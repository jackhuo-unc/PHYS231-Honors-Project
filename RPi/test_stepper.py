#!/usr/bin/env python3
"""
Stepper motor sanity test - slower, with proper pin shutdown.
"""
import RPi.GPIO as GPIO
import time

STEP_PIN = 20
DIR_PIN = 21
STEPS_PER_REV = 200
STEP_DELAY = 0.010      # was 0.005 - now 10ms per step (100 Hz, slower & more reliable)

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(STEP_PIN, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(DIR_PIN, GPIO.OUT, initial=GPIO.LOW)

def step(n, direction):
    GPIO.output(DIR_PIN, direction)
    time.sleep(0.001)
    for _ in range(n):
        GPIO.output(STEP_PIN, GPIO.HIGH)
        time.sleep(STEP_DELAY / 2)
        GPIO.output(STEP_PIN, GPIO.LOW)
        time.sleep(STEP_DELAY / 2)

try:
    print("Forward 1 revolution...")
    step(STEPS_PER_REV, GPIO.HIGH)
    time.sleep(1)
    print("Reverse 1 revolution...")
    step(STEPS_PER_REV, GPIO.LOW)
    time.sleep(1)
    print("Done.")
finally:
    GPIO.output(STEP_PIN, GPIO.LOW)
    GPIO.output(DIR_PIN, GPIO.LOW)
    # Note: deliberately NOT calling GPIO.cleanup() - it leaves pins floating
    print("Pins held LOW. Motor should be silent.")