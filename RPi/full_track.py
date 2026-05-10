#!/usr/bin/env python3

import cv2
import numpy as np
import RPi.GPIO as GPIO
import time
import threading
from picamera2 import Picamera2

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
KP = 0.04
KI = 0.00          
KD = 0.03        
DEADBAND_PX = 20
MAX_STEP_DEG = 10.0
MANUAL_STEP_DEG = 5.0

# --- PID state ---
prev_error = 0.0
integral = 0.0
prev_time = time.monotonic()

# --- Setup ---
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(STEP_PIN,   GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(DIR_PIN,    GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(ENABLE_PIN, GPIO.OUT, initial=GPIO.HIGH)

# --- Stepper worker thread state ---
target_angle  = STEPPER_START   # where we want to be (set by main thread)
current_angle = STEPPER_START   # where we actually are (updated by worker)
target_lock = threading.Lock()
shutdown    = threading.Event()
new_target  = threading.Event()


def stepper_worker():
    """
    Background thread. Continuously checks if we need to step toward the target,
    and steps one microstep at a time. The driver is enabled only while moving.
    """
    global current_angle
    driver_enabled = False

    while not shutdown.is_set():
        with target_lock:
            tgt = target_angle
            cur = current_angle

        diff = tgt - cur

        if abs(diff) < DEG_PER_STEP:
            # At target - disable driver if it was running, then sleep waiting
            if driver_enabled:
                GPIO.output(ENABLE_PIN, GPIO.HIGH)
                driver_enabled = False
            new_target.wait(timeout=0.1)
            new_target.clear()
            continue

        # Need to move. Enable driver if not already.
        if not driver_enabled:
            GPIO.output(ENABLE_PIN, GPIO.LOW)
            time.sleep(0.001)
            driver_enabled = True

        # Set direction based on sign of diff
        if diff > 0:
            GPIO.output(DIR_PIN, DIR_POSITIVE)
            step_dir = 1
        else:
            GPIO.output(DIR_PIN, DIR_NEGATIVE)
            step_dir = -1
        # No need for big DIR settle here - we set it once per direction change
        # (it gets re-set every loop iteration but the value rarely actually changes)

        # Take one microstep
        GPIO.output(STEP_PIN, GPIO.HIGH)
        time.sleep(STEP_PULSE_WIDTH)
        GPIO.output(STEP_PIN, GPIO.LOW)
        time.sleep(STEP_PULSE_WIDTH)

        with target_lock:
            current_angle += step_dir * DEG_PER_STEP

    # On shutdown
    GPIO.output(ENABLE_PIN, GPIO.HIGH)


def request_move(new_target_angle):
    """Main-thread function: tell the worker to head to a new angle."""
    global target_angle
    new_target_angle = max(STEPPER_MIN_DEG, min(STEPPER_MAX_DEG, new_target_angle))
    with target_lock:
        target_angle = new_target_angle
    new_target.set()


# Launch the stepper worker
worker = threading.Thread(target=stepper_worker, daemon=True)
worker.start()

# --- Camera ---
picam2 = Picamera2()
picam2.configure(picam2.create_preview_configuration(
    main={"size": (FRAME_W, FRAME_H), "format": "RGB888"}
))
picam2.start()
time.sleep(1)

AUTO_MODE = False

print("Tracker running.")
print("  q = quit | m = toggle auto/manual | a/d = pan | c = recenter")

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
        
        now = time.monotonic()
        dt = now - prev_time
        prev_time = now

        if AUTO_MODE and error_x is not None and abs(error_x) > DEADBAND_PX:
            # P term
            p_term = KP * error_x
            
#             with target_lock:
#                 motor_at_rest = abs(target_angle - current_angle) < DEG_PER_STEP

            # I term (with anti-windup clamp)
#             if motor_at_rest:
            integral += error_x * dt
            integral = max(-200, min(200, integral))   # clamp to prevent windup
            i_term = KI * integral

            # D term - rate of change of error
            if dt > 0:
                derivative = (error_x - prev_error) / dt
            else:
                derivative = 0.0
            d_term = KD * derivative

            # Combined output
            delta = -(p_term + i_term + d_term)
            delta = max(-MAX_STEP_DEG, min(MAX_STEP_DEG, delta))

            with target_lock:
                next_target = target_angle + delta
            request_move(next_target)

            prev_error = error_x
        else:
            # No target / inside deadband - reset derivative state
            # so we don't get a huge spike when the target reappears
            prev_error = error_x if error_x is not None else 0.0
            # Slowly bleed off the integral term too
            integral *= 0.9

        # Snapshot current angle for display
        with target_lock:
            display_angle = current_angle

        cv2.line(bgr, (FRAME_W // 2, 0), (FRAME_W // 2, FRAME_H), (255, 255, 255), 1)
        mode_label = "AUTO" if AUTO_MODE else "MANUAL"
        mode_color = (0, 255, 0) if AUTO_MODE else (0, 165, 255)
        cv2.putText(bgr, f"MODE: {mode_label}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, mode_color, 2)
        status = f"err={error_x:+d}px angle={display_angle:+.1f}deg" if error_x is not None \
                 else f"no target angle={display_angle:+.1f}deg"
        cv2.putText(bgr, status, (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        cv2.imshow("Tracker", bgr)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('m'):
            AUTO_MODE = not AUTO_MODE
            print(f"Switched to {'AUTO' if AUTO_MODE else 'MANUAL'} mode")
        elif key == ord('c'):
            request_move(STEPPER_START)
        elif not AUTO_MODE:
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
    new_target.set()      # wake the worker so it can see shutdown
    worker.join(timeout=1)
    picam2.stop()
    cv2.destroyAllWindows()
    GPIO.output(ENABLE_PIN, GPIO.HIGH)
    GPIO.output(STEP_PIN, GPIO.LOW)
    GPIO.output(DIR_PIN,  GPIO.LOW)
    print("Driver disabled, pins held LOW. Motor silent.")