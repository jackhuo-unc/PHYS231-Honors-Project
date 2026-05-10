#!/usr/bin/env python3
"""
Stage 3: Servo sanity check.
Sweeps the servo from 0 to 180 degrees and back.
"""
import time
# from gpiozero import AngularServo
import RPi.GPIO as GPIO

gpio_pin = 14

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(gpio_pin, GPIO.OUT)

pwm=GPIO.PWM(gpio_pin, 50)
pwm.start(0)


# servo = AngularServo(
#     14,                       # GPIO pin
#     min_angle=-90,
#     max_angle=90,
#     min_pulse_width=0.0005,   # 0.5 ms — adjust if servo doesn't reach full range
#     max_pulse_width=0.0025,   # 2.5 ms
# )

try:
    print("Sweeping...")
    for angle in range(-90, 91, 10):
#         servo.angle = angle
        pwm.ChangeDutyCycle(2.5) # -90 deg position
        time.sleep(1)
        pwm.ChangeDutyCycle(7.5) # neutral position
        time.sleep(1)
        pwm.ChangeDutyCycle(12)  # +90 deg position
        time.sleep(1)
        print(f"  angle = {angle:+d}")
        time.sleep(3)
    for angle in range(90, -91, -10):
        servo.angle = angle
        print(f"  angle = {angle:+d}")
        time.sleep(3)
    servo.angle = 0
    time.sleep(3)
finally:
    servo.detach()
    print("Done.")