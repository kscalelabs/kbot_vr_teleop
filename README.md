# K-Scale VR Teleoperation

This repo lets you control the upper body of K-Bot with a VR headset, using either the controllers or hand tracking.

## Setup
Requirements to set up:
### K-Bot
Setup:
  - Arms plugged in, legs don't need to be plugged in
  - Running version of rust firmware package corresponding to whether or not you have grippers plugged in
    - With grippers: [`eric/5dof-with-grippers`](https://github.com/kscalelabs/firmware/commit/b89560d7fa3d254c0eee6f6acfbf93f9d12f8309)
    - Without grippers: [`eric/can-imu-emulator`](https://github.com/kscalelabs/firmware/commit/0f9462c4cc91a866b72fbf107219c035ce7c5e61)
    - See further down this document for a guide on how to set this up
  - CSI Cameras plugged in
  - Gstreamer installed and `gi` python package installed, with webrtc plugins

Commands to run:
  - `gstreamer.py`
  - `deploy_from_queue`

### Intermediate computer (can also be run on the K-Bot, but the raspberry pi struggles to encode the video stream while doing invserse kinematics and running a policy). Running the signaling server on the pi would also need a refactor of the https proxy logic since it assumes the web server and signaling server use the same IP.

Setup:
  - Install `uv`
  - Clone this repo
  - Install `node`
  - cd into `webxrtest` and `npm i`

Commands to run:
  - cd into `webxrtest` and `npm run start-https`
  - In a separate terminal, `uv run src/kscale_vr_teleop/signaling.py`

### In the headset
  - Connect to the ip of the intermediate computer, port 8443, with https (e.g. `https://10.33.13.41:8443`)
  - Enter the IP address of the K-Bot.
  - Press Connect. This will start an immersive VR session with hand-tracking.
  - Handtracking will work if both hands are found, otherwise controller positions are used. Using a controller, "X" pauses/resumes sending commands to the robot and the back triggers close the grippers.




## Details for K-Bot Setup
For this VR teleop repo to work, you need to have K-Bot set up with the [kbot deployment](https://github.com/kscalelabs/kbot_deployment), [k-log](https://github.com/kscalelabs/klog), and [firmware](https://github.com/kscalelabs/firmware/commit/b89560d7fa3d254c0eee6f6acfbf93f9d12f8309) repositories. These are the same three that are required to run a locomotion policy. You will probably also want the [robstride](https://github.com/kscalelabs/robstride) repo fo debugging motor connections. Right now `kbot_deployment` has a lot of dependencies on specific hosts on the network at the K-Scale house but you can make it work without internet by commenting out the `rsync` part of `deploy_from_queue` and hard-coding a policy to select. This seeming over-complication comes from the fact that the teleop stack is built in a way where eventually you will be able to control the robot while it is running a policy to balance on its legs or move around in response to joystick commands. Right now we have two "dummy" policies that just send all zeros to the legs and pass the arm joint commands straight from the observation vector to the actions.
