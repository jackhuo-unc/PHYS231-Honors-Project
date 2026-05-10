#!/usr/bin/env python3
"""Sends fake yaw values to the Pi tracker as a sweep."""
import socket
import struct
import time
import math

PI_IP   = "172.20.10.13"   # CHANGE to your Pi's IP
PI_PORT = 5005

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
print(f"Sending to {PI_IP}:{PI_PORT} - Ctrl+C to stop")

t0 = time.monotonic()
while True:
    t = time.monotonic() - t0
    yaw   = 30.0 * math.sin(t * 0.5)   # sweeps -30 to +30 degrees
    pitch = 0.0
    sock.sendto(struct.pack("<ff", yaw, pitch), (PI_IP, PI_PORT))
    time.sleep(0.02)   # 50 Hz updates
