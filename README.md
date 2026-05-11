# Jack Huo Honors Project: VR-Controlled Camera Tracking System

---

## Project Overview

This project walks through building a Raspberry Pi 5 system that:

1. Detects a blue-colored object via the V2 camera using OpenCV  
2. Drives a NEMA 17 stepper motor (via A4988 driver) to physically rotate the camera so the target stays centered in frame  
3. Accepts manual control from the keyboard, manual yaw input from a Meta Quest 3S over UDP, and an auto tracking mode  
4. Displays the video on screen, and streams the annotated video back to the headset over MJPEG for in-VR display. 


Demo videos: \[[link](https://drive.google.com/drive/u/0/folders/1h98j5W_vXnf6YvJ9lZxpEqliyoAab54F)\]  
Source code: \[[link](https://github.com/jackhuo-unc/PHYS231-Honors-Project)\]

---

## Bill of Materials

### Compute and Camera

| Item | Notes | Link |
| :---- | :---- | :---- |
| Raspberry Pi 5 (4GB or 8GB) | Tested on Bookworm/Trixie | \[[link](https://www.amazon.com/dp/B0CK3L9WD3)\] |
| microSD card (32 GB+) | Class 10 or better | \[[link](http://amazon.com/dp/B0G8KLQ64L)\] |
| USB-C power supply | The Pi 5 needs more current than older PSUs provide. I just used the USB-C cable from my MacBook | — |
| Raspberry Pi V2 camera module | 8MP IMX219 sensor. Loaned from Dr. J. | \[[link](https://www.amazon.com/Arducam-IMX219-Raspberry-Distortion-Compatible/dp/B09VSRH14M/ref=sr_1_12?crid=1R4P4LLR9DC0Y&dib=eyJ2IjoiMSJ9.qLZqhX7jjrgA9W9w2HPv2WW8DXYbFTRTaYduey18mYuBd4TglajIw9lGcNNwj1yzoApLv8wHssd_-ZQ_xg7GDk_HZ2ssDRJZxGgRPwLZA-vpCIPK-iRLsZqiDbd7xQ2xM4bQqNZxoUX0sGonqi0Gks1qKQYOxMTRv9xwv6RKG9kRUPMdzqaAU1n0dOM2Km9o429JsrM29fyh7yGLFFBlKKADDqe_ql5I4jNH6yp3gVM.hVr7dw_mrEng_5VzkiK7XLxzv9VfvZ5O1KOJXXrj84Y&dib_tag=se&keywords=8mp%2Bimx219&qid=1778177542&sprefix=8mp%2Bimx21%2Caps%2C139&sr=8-12&th=1)\] I think this is the right one.  |
| **Pi 5 camera ribbon cable (15-pin to 22-pin)** | The V2 camera has a 22-pin port. It ships with both a 15-pin and a 22-pin cable. The Pi 5 has a 22-pin port. The box the camera came in had a 22-pin cable already, but otherwise, you’ll need an adapter. | — |
| Micro-HDMI to HDMI adapter | The RPi uses micro-HDMI. Most monitors use HDMI | \[[link](https://www.amazon.com/dp/B09LYPXPH6)\] |
| HDMI display monitor, USB keyboard, USB mouse | For initial Pi setup | — |
| RPi metal case and cooling unit | Needed for heat dissipation | \[[link](https://www.amazon.com/dp/B0CMZ84GM8?ref=ppx_yo2ov_dt_b_fed_asin_title)\] |

### Stepper Motor and Driver

| Item | Notes | Link |
| :---- | :---- | :---- |
| NEMA 17 stepper motor | Standard 1.8°/step, 4-wire bipolar | \[[link](https://www.amazon.com/dp/B0FP1RNPXJ?ref=ppx_yo2ov_dt_b_fed_asin_title)\] |
| A4988 stepper driver module | On a breakout PCB | \[[link](https://www.amazon.com/dp/B07BND65C8?ref=ppx_yo2ov_dt_b_fed_asin_title)\] |
| 12V DC switching power supply, ≥5A (10A used here) | Bare-wire screw-terminal output type | \[[link](https://www.amazon.com/dp/B08BHSNY7F?ref=ppx_yo2ov_dt_b_fed_asin_title)\] |
| 3-Prong power cord | Connects the power supply to a wall outlet | \[[link](https://www.amazon.com/dp/B0FKTBKS9L?ref=ppx_yo2ov_dt_b_fed_asin_title)\] |
| 47µF / 35V electrolytic capacitor | Across VMOT and GND on the A4988. Got this from the parts kit | — |
| Half-size breadboard | — | \[[link](https://www.amazon.com/dp/B07DL13RZH?ref=ppx_yo2ov_dt_b_fed_asin_title)\] |
| Jumper wires (M-M and M-F assortment) | — | \[[link](https://www.amazon.com/dp/B01EV70C78?ref=ppx_yo2ov_dt_b_fed_asin_title)\] |
| Small flathead screwdriver | For A4988 current-limit pot and for setting up the power supply | — |
| Duct tape | For fixing the camera to the motor | \[[link](https://www.amazon.com/dp/B09D8GL5FL?ref_=ppx_hzsearch_conn_dt_b_fed_asin_title_1&th=1)\] |

### VR

| Item | Notes | Link |
| :---- | :---- | :---- |
| Meta Quest 3S | Tested model | \[[link](https://www.amazon.com/dp/B0F2GYMC8H?ref=ppx_yo2ov_dt_b_fed_asin_title&th=1)\] |
| Meta developer account | Required for sideloading via Developer Hub | \[[link](https://developers.meta.com/horizon/)\] |
| Mac or PC running Unity | Used Unity 2022 LTS with Mixed Reality template, running on a 2025 MacBook Air 13-inch Laptop with M4 chip: 24GB Unified Memory, 512GB SSD Storage | \[[link](https://unity.com/products/unity-personal)\] |
| USB-C cable (Mac ↔ Quest) | For Quest Link / sideloading builds | — |

If you use a Windows machine, you are able to connect your headset via [Meta Quest Link](https://www.meta.com/help/quest/509273027107091/), which allows you to run and test directly from Unity. Otherwise, you’ll need to compile/build, and run, which takes longer. A powerful computer is needed for this, otherwise build times can take more than half an hour.

TLDR list of steps:

* Reviewed the curated honors project list; identified RPi \+ camera as the natural fit given prior OpenCV / Linux experience.  
* Brainstormed a base goal (autonomous camera tracking) and a stretch goal (Meta Quest 3S integration with manual control \+ video feedback).  
* Drafted abstract, goals, and staged technical objectives: explicitly structured so each subsystem could be verified before integration.  
* Installed Raspberry Pi OS Bookworm on Pi 5; verified terminal/keyboard/monitor setup.  
* Installed picamera2, OpenCV, NumPy, and RPi.GPIO.  
* Wrote detect.py using picamera2 \+ OpenCV: HSV mask → erode/dilate → largest contour → bounding box → centroid → pixel error.  
* Verified detection visually with a blue object (red/orange on camera) before adding any motor logic.  
* Tested with a small 3-wire servo to GPIO 14 (signal) \+ 5V \+ GND directly off the Pi.  
* Wrote a sweep test and then combined it with the detection pipeline into a closed-loop tracker.  
* Added a manual / auto mode toggle so the demo could show keyboard control vs. camera control side by side.  
* Switched the servo motor for a NEMA 17 \+ A4988 \+ 12V power supply for proper torque and to eliminate Pi brownout issues.  
* Wired up the A4988 with separate motor power (VMOT) and logic power (VDD), with shared ground.  
* Wired NEMA 17 coils to A1/A2 and B1/B2 (black+green \= one coil, blue+red \= the other).  
* Used a screwdriver to set the current-limit pot on the A4988.  
* Tested with a simple step/direction script before integration.  
* Replaced all servo logic with RPi.GPIO-based step/direction pulses.  
* Added the ENABLE pin to prevent phantom stepping from electrical noise.  
* Moved stepper movement to a background thread so the video stream stayed smooth during long microstepped moves.  
* Tuned proportional control, then added integral term for steady-state error and derivative term for overshoot.  
* Got Meta Developer Hub set up; verified MacBook ↔ headset connection over USB-C link.  
* Built a Unity scene with a NetworkSender GameObject that read controller joystick input and sent yaw/pitch over UDP to the Pi's IP on port 5005\.  
* Wrote a UDP receiver thread on the Pi that fed yaw values into the same stepper target as the auto-tracker.  
* Implemented mode switching on the Pi: AUTO (camera-driven) vs. VR (joystick-driven).  
* Added MJPEG video streaming back from Pi to a Unity texture quad inside the headset's scene so the user could see the camera's view in VR.

For a full list of steps/instructions with screenshots, you can find them [here](https://docs.google.com/document/d/1QE3tAvdssT93oJv5-lcgaeRkqQElxRBhty5j7keP9lc/edit?tab=t.0). 
