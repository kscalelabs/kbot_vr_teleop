# K-Scale VR Teleoperation

This repo lets you control the upper body of K-Bot with a VR headset, using either the controllers or hand tracking.

## Setup
Requirements to set up:
- K-Bot
  - Arms plugged in, legs don't need to be plugged in
  - Running version of rust firmware package corresponding to whether or not you have grippers plugged in
    - With grippers: [`eric/5dof-with-grippers`](https://github.com/kscalelabs/firmware/commit/b89560d7fa3d254c0eee6f6acfbf93f9d12f8309)
    - Without grippers: [`eric/can-imu-emulator`](https://github.com/kscalelabs/firmware/commit/0f9462c4cc91a866b72fbf107219c035ce7c5e61)
    - Refer to another K-Scale employee for how to set this up, right now the docs are pretty lacking everywhere
  - CSI Cameras plugged in
  - Gstreamer installed and `gi` python package installed
  - Run `gstreamer.py`


- Intermediate computer (can also be run on the K-Bot, but the raspberry pi gets way too slow when running both software encoding for the video stream and the invserse kinematics)
  - Install `uv`
  - Clone this repo
  - Install `node`
  - cd into `webxrtest` and `npm i`, then `npm run start-https`
  - Change hard-coded IP address of the robot throughout the codebase
  - In a separate terminal, `uv run src/kscale_vr_teleop/signaling.py`

- In the headset
  - Connect to the ip of the intermediate computer, port 8443, with https
  - Click connect and then start VR button that pops up
