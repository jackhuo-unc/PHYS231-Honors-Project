#!/usr/bin/env python3

import cv2
import numpy as np
import RPi.GPIO as GPIO
import time
import threading
import socket
import struct
from picamera2 import Picamera2
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

# --- Camera / detection ---
FRAME_W, FRAME_H = 640, 480
HSV_LOWER = np.array([0, 120, 100])
HSV_UPPER = np.array([15, 255, 255])
MIN_AREA = 500

# --- Stepper motor ---
STEP_PIN   = 20
DIR_PIN    = 21
ENABLE_PIN = 16

MICROSTEPS    = 16
STEPS_PER_REV = 200 * MICROSTEPS
DEG_PER_STEP  = 360.0 / STEPS_PER_REV

STEP_PULSE_WIDTH = 0.001

STEPPER_MIN_DEG = -90.0
STEPPER_MAX_DEG = 90.0
STEPPER_START   = 0.0

DIR_POSITIVE = GPIO.LOW
DIR_NEGATIVE = GPIO.HIGH

# --- Control ---
KP = 0.05
KI = 0.002
KD = 0.04
DEADBAND_PX = 15
MAX_STEP_DEG = 10.0
MANUAL_STEP_DEG = 5.0

# --- VR / UDP ---                                    # NEW SECTION
UDP_LISTEN_PORT = 5005
VR_YAW_DEADZONE_DEG = 2    # smaller yaw changes are ignored

# Packet types
PACKET_TYPE_ABSOLUTE = 0    # yaw is an absolute target angle
PACKET_TYPE_VELOCITY = 1    # yaw is a velocity (deg/sec)

# --- Setup ---
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(STEP_PIN,   GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(DIR_PIN,    GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(ENABLE_PIN, GPIO.OUT, initial=GPIO.HIGH)

# --- Stepper worker thread state ---
target_angle  = STEPPER_START
current_angle = STEPPER_START
target_lock = threading.Lock()
shutdown    = threading.Event()
new_target  = threading.Event()

# --- MJPEG streaming ---
HTTP_PORT = 8080
JPEG_QUALITY = 70	#50-90. Lower = smaller packets, faster

# shared latest frame for streaming
latest_jpeg = None
latest_jpeg_lock = threading.Lock()


def stepper_worker():
    global current_angle
    driver_enabled = False

    while not shutdown.is_set():
        with target_lock:
            tgt = target_angle
            cur = current_angle

        diff = tgt - cur

        if abs(diff) < DEG_PER_STEP:
            if driver_enabled:
                GPIO.output(ENABLE_PIN, GPIO.HIGH)
                driver_enabled = False
            new_target.wait(timeout=0.1)
            new_target.clear()
            continue

        if not driver_enabled:
            GPIO.output(ENABLE_PIN, GPIO.LOW)
            time.sleep(0.001)
            driver_enabled = True

        if diff > 0:
            GPIO.output(DIR_PIN, DIR_POSITIVE)
            step_dir = 1
        else:
            GPIO.output(DIR_PIN, DIR_NEGATIVE)
            step_dir = -1

        GPIO.output(STEP_PIN, GPIO.HIGH)
        time.sleep(STEP_PULSE_WIDTH)
        GPIO.output(STEP_PIN, GPIO.LOW)
        time.sleep(STEP_PULSE_WIDTH)

        with target_lock:
            current_angle += step_dir * DEG_PER_STEP

    GPIO.output(ENABLE_PIN, GPIO.HIGH)


def request_move(new_target_angle):
    global target_angle
    new_target_angle = max(STEPPER_MIN_DEG, min(STEPPER_MAX_DEG, new_target_angle))
    with target_lock:
        target_angle = new_target_angle
    new_target.set()


# --- VR UDP listener thread ---                       # NEW SECTION
# Stores latest yaw/pitch received from the Quest
vr_state = {
    "type": PACKET_TYPE_ABSOLUTE,
    "yaw": 0.0,
    "pitch": 0.0,
    "last_update": 0.0
}
vr_state_lock = threading.Lock()


def udp_listener():
    """
    Packet format: [type:1 byte][padding:3 bytes][yaw:float32][pitch:float32]
    type 0 = absolute angle, type 1 = velocity (deg/sec)
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", UDP_LISTEN_PORT))
    sock.settimeout(0.5)
    print(f"UDP listener bound to port {UDP_LISTEN_PORT}")

    while not shutdown.is_set():
        try:
            data, addr = sock.recvfrom(64)
#             print(f"UDP packet from {addr}: {len(data)} bytes")
            if len(data) >= 12:
                packet_type = data[0]
                yaw, pitch = struct.unpack("<ff", data[4:12])
#                 print(f"UDP recv: yaw={yaw:+.1f} pitch={pitch:+.1f}")
                with vr_state_lock:
                    vr_state["type"] = packet_type
                    vr_state["yaw"]   = yaw
                    vr_state["pitch"] = pitch
                    vr_state["last_update"] = time.monotonic()
                
        except socket.timeout:
            continue
        except Exception as e:
            print(f"UDP error: {e}")

    sock.close()

class MJPEGHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/stream":
            self.send_response(404)
            self.end_headers()
            return

        boundary = "frameboundary"
        self.send_response(200)
        self.send_header("Content-Type",
                         f"multipart/x-mixed-replace; boundary={boundary}")
        self.send_header("Cache-Control", "no-cache, private")
        self.send_header("Pragma", "no-cache")
        self.end_headers()

        try:
            while not shutdown.is_set():
                with latest_jpeg_lock:
                    frame = latest_jpeg
                if frame is None:
                    time.sleep(0.05)
                    continue

                self.wfile.write(f"--{boundary}\r\n".encode())
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                self.wfile.write(frame)
                self.wfile.write(b"\r\n")
                time.sleep(0.033)   # cap at ~30 fps
        except (BrokenPipeError, ConnectionResetError):
            pass  # client disconnected, normal

    def log_message(self, *args):
        pass  # silence default per-request logging


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def http_server_thread():
    server = ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), MJPEGHandler)
    print(f"HTTP MJPEG server on :{HTTP_PORT}/stream")
    while not shutdown.is_set():
        server.handle_request()

# Launch threads
worker = threading.Thread(target=stepper_worker, daemon=True)
worker.start()
udp_thread = threading.Thread(target=udp_listener, daemon=True)
udp_thread.start()
http_thread = threading.Thread(target=http_server_thread, daemon=True)
http_thread.start()

# --- Camera ---
picam2 = Picamera2()
picam2.configure(picam2.create_preview_configuration(
    main={"size": (FRAME_W, FRAME_H), "format": "RGB888"}
))
picam2.start()
time.sleep(1)

# --- Modes ---                                        # MODIFIED
MODE_MANUAL = 0
MODE_AUTO   = 1
MODE_VR     = 2
MODE_NAMES  = ["MANUAL", "AUTO", "VR"]
MODE_COLORS = [(0, 165, 255), (0, 255, 0), (255, 0, 255)]
mode = MODE_MANUAL

# --- PID state ---
prev_error = 0.0
integral = 0.0
prev_time = time.monotonic()

# --- VR state ---
vr_yaw_zero = None  # captured the first time VR mode is entered
vr_yaw_filtered = None
VR_FILTER_ALPHA = 0.3        # 0=infinite smoothing, 1=no smoothing
VR_UPDATE_INTERVAL = 0.1     # seconds - update motor target at most 10 Hz
last_vr_motor_update = 0.0

print("Tracker running.")
print("  q = quit | m = cycle modes (MANUAL > AUTO > VR)")
print("  a/d = pan (manual) | c = recenter | z = re-zero VR yaw")

try:
    while True:
        frame = picam2.capture_array()
        bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

        mask = cv2.inRange(hsv, HSV_LOWER, HSV_UPPER)
        mask = cv2.erode(mask, None, iterations=2)
        mask = cv2.dilate(mask, None, iterations=2)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        error_x = None
        if contours:
            largest = max(contours, key=cv2.contourArea)
            if cv2.contourArea(largest) > MIN_AREA:
                x, y, w, h = cv2.boundingRect(largest)
                cx = x + w // 2
                cy = y + h // 2
                error_x = cx - FRAME_W // 2

                cv2.rectangle(bgr, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.circle(bgr, (cx, cy), 5, (0, 0, 255), -1)

        # --- Mode-specific control ---
        now = time.monotonic()
        dt = now - prev_time
        prev_time = now

        if mode == MODE_AUTO and error_x is not None and abs(error_x) > DEADBAND_PX:
            p_term = KP * error_x
            with target_lock:
                motor_at_rest = abs(target_angle - current_angle) < DEG_PER_STEP
            if motor_at_rest:
                integral += error_x * dt
                integral = max(-200, min(200, integral))
            i_term = KI * integral
            derivative = (error_x - prev_error) / dt if dt > 0 else 0.0
            d_term = KD * derivative
            delta = -(p_term + i_term + d_term)
            delta = max(-MAX_STEP_DEG, min(MAX_STEP_DEG, delta))
            with target_lock:
                next_target = target_angle + delta
            request_move(next_target)
            prev_error = error_x

        elif mode == MODE_VR:
            with vr_state_lock:
                vr_type = vr_state["type"]
                vr_yaw = vr_state["yaw"]
                vr_age = now - vr_state["last_update"]

            if vr_age < 1.0:  # only act on fresh data
                if vr_type == PACKET_TYPE_VELOCITY:
                    # Joystick mode: yaw is in deg/sec
                    # Update target based on stick deflection and elapsed time
                    velocity_deg_per_sec = vr_yaw
                    if abs(velocity_deg_per_sec) > 1.0:  # small deadzone for stick
                        delta = - velocity_deg_per_sec * dt
                        with target_lock:
                            next_tgt = target_angle + delta
                        next_tgt = max(STEPPER_MIN_DEG, min(STEPPER_MAX_DEG, next_tgt))
                        request_move(next_tgt)
                else:
                    # Absolute mode (head tracking)
                    if vr_yaw_zero is None:
                        vr_yaw_zero = vr_yaw  # capture initial yaw as the "zero" reference
                        vr_yaw_filtered = vr_yaw
                        
                    # Low-pass filter the yaw to smooth out jitter
                    vr_yaw_filtered = (VR_FILTER_ALPHA * vr_yaw + (1 - VR_FILTER_ALPHA) * vr_yaw_filtered)
                    
                    desired_angle = -(vr_yaw_filtered - vr_yaw_zero)  # negate if direction is flipped
                    desired_angle = max(STEPPER_MIN_DEG, min(STEPPER_MAX_DEG, desired_angle))
                    
                    if now - last_vr_motor_update >= VR_UPDATE_INTERVAL:
                        with target_lock:
                            current_target = target_angle
                        if abs(desired_angle - current_target) > 0.2:  # tiny threshold
                            request_move(desired_angle)
                            last_vr_motor_update = now
#                 
#                     # Read target_angle, release lock, then act
#                     with target_lock:
#                         current_target = target_angle
#                     
#                     if abs(desired_angle - current_target) > VR_YAW_DEADZONE_DEG:
#                         request_move(desired_angle)

        else:
            prev_error = error_x if error_x is not None else 0.0
            integral *= 0.9

        # --- Overlay ---
        with target_lock:
            display_angle = current_angle
        with vr_state_lock:
            vr_age = now - vr_state["last_update"]

        cv2.line(bgr, (FRAME_W // 2, 0), (FRAME_W // 2, FRAME_H), (255, 255, 255), 1)
        cv2.putText(bgr, f"MODE: {MODE_NAMES[mode]}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, MODE_COLORS[mode], 2)
        status = f"err={error_x:+d}px angle={display_angle:+.1f}deg" if error_x is not None \
                 else f"no target angle={display_angle:+.1f}deg"
        cv2.putText(bgr, status, (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        if mode == MODE_VR:
            link_status = "LINK OK" if vr_age < 1.0 else "NO VR DATA"
            link_color = (0, 255, 0) if vr_age < 1.0 else (0, 0, 255)
            cv2.putText(bgr, link_status, (10, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, link_color, 2)
            
        #encode for streaming
        ok, jpeg_buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if ok:
            with latest_jpeg_lock:
                latest_jpeg = jpeg_buf.tobytes()

        cv2.imshow("Tracker", bgr)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('m'):
            mode = (mode + 1) % 3
            print(f"Switched to {MODE_NAMES[mode]} mode")
            if mode != MODE_VR:
                vr_yaw_zero = None  # reset VR zero on exit
            integral = 0.0  # reset PID state on mode change
        elif key == ord('c'):
            request_move(STEPPER_START)
        elif key == ord('z'):
            with vr_state_lock:
                vr_yaw_zero = vr_state["yaw"]
            print("VR yaw re-zeroed")
        elif mode == MODE_MANUAL:
            if key == ord('a') or key == 81:
                with target_lock:
                    next_target = target_angle + MANUAL_STEP_DEG
                request_move(next_target)
            elif key == ord('d') or key == 83:
                with target_lock:
                    next_target = target_angle - MANUAL_STEP_DEG
                request_move(next_target)

finally:
    shutdown.set()
    new_target.set()
    worker.join(timeout=1)
    udp_thread.join(timeout=1)
    picam2.stop()
    cv2.destroyAllWindows()
    GPIO.output(ENABLE_PIN, GPIO.HIGH)
    GPIO.output(STEP_PIN, GPIO.LOW)
    GPIO.output(DIR_PIN,  GPIO.LOW)
    print("Driver disabled, pins held LOW. Motor silent.")