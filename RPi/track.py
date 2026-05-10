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

# --- Servo (RPi.GPIO style) ---
SERVO_PIN = 14
SERVO_FREQ = 50          # 50 Hz standard for hobby servos
# Duty cycle calibration from your working code:
#   2.5% = -90 deg
#   7.5% =   0 deg
#  12.0% = +90 deg
DUTY_AT_MIN = 2.5
DUTY_AT_MAX = 12.0
SERVO_MIN = -90.0
SERVO_MAX = 90.0
SERVO_START = 0.0

SERVO_UPDATE_INTERVAL = 1.0   # seconds between servo commands

# --- Control ---
KP = 0.05
DEADBAND_PX = 30
MAX_STEP_DEG = 1.0
MANUAL_STEP_DEG = 2.0

# --- Quiet operation ---
PULSE_HOLD_TIME = 0.25   # how long to hold a PWM pulse before stopping it
                         # longer = more reliable movement, more buzz
                         # shorter = quieter, may not reach target

# --- Setup ---
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(SERVO_PIN, GPIO.OUT)
pwm = GPIO.PWM(SERVO_PIN, SERVO_FREQ)
pwm.start(0)              # start with 0% duty (no signal = silent)

current_angle = SERVO_START
last_command_time = 0.0
stop_timer = None
pwm_lock = threading.Lock()


def angle_to_duty(angle):
    """Convert angle in degrees to PWM duty cycle %."""
    angle = max(SERVO_MIN, min(SERVO_MAX, angle))
    # Linear interpolation between min/max calibration points
    return DUTY_AT_MIN + (angle - SERVO_MIN) * (DUTY_AT_MAX - DUTY_AT_MIN) / (SERVO_MAX - SERVO_MIN)


def stop_pwm():
    """Cut the PWM signal so the servo goes silent."""
    with pwm_lock:
        pwm.ChangeDutyCycle(0)


def move_servo(target_angle):
    """
    Pulse the servo just long enough to move, then go silent.
    Rate-limited so the 5V rail has time to recover between movements.
    """
    global current_angle, stop_timer, last_command_time

    now = time.monotonic()
    if now - last_command_time < SERVO_UPDATE_INTERVAL:
        return  # too soon since last move - skip

    target_angle = max(SERVO_MIN, min(SERVO_MAX, target_angle))
    if abs(target_angle - current_angle) < 0.5:
        return

    duty = angle_to_duty(target_angle)
    with pwm_lock:
        pwm.ChangeDutyCycle(duty)
    current_angle = target_angle
    last_command_time = now

    if stop_timer is not None:
        stop_timer.cancel()
    stop_timer = threading.Timer(PULSE_HOLD_TIME, stop_pwm)
    stop_timer.start()

# --- Initial centering ---
move_servo(SERVO_START)
time.sleep(1)

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

        # --- AUTO mode tracking ---
        if AUTO_MODE and error_x is not None and abs(error_x) > DEADBAND_PX:
            delta = -KP * error_x
            delta = max(-MAX_STEP_DEG, min(MAX_STEP_DEG, delta))
            move_servo(current_angle + delta)

        # --- Overlay ---
        cv2.line(bgr, (FRAME_W // 2, 0), (FRAME_W // 2, FRAME_H), (255, 255, 255), 1)
        mode_label = "AUTO" if AUTO_MODE else "MANUAL"
        mode_color = (0, 255, 0) if AUTO_MODE else (0, 165, 255)
        cv2.putText(bgr, f"MODE: {mode_label}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, mode_color, 2)
        status = f"err={error_x:+d}px angle={current_angle:+.1f}deg" if error_x is not None \
                 else f"no target angle={current_angle:+.1f}deg"
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
            move_servo(SERVO_START)
        elif not AUTO_MODE:
            if key == ord('a') or key == 81:
                move_servo(current_angle - MANUAL_STEP_DEG)
            elif key == ord('d') or key == 83:
                move_servo(current_angle + MANUAL_STEP_DEG)

finally:
    if stop_timer is not None:
        stop_timer.cancel()
    picam2.stop()
    cv2.destroyAllWindows()
    pwm.ChangeDutyCycle(angle_to_duty(SERVO_START))
    time.sleep(0.5)
    pwm.stop()
    GPIO.cleanup()
