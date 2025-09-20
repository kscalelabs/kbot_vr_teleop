# Miscellaneous Notes

This document is for explaining the _why_ behind some of the technical decisions for this project and suggests some future work directions.

## Justifications for some decisions in the project

Most other VR teleop projects have a similar structure, where you have some web app running in the VR headset, connected to some python program that does inverse kinematics and reads images from the camera on the robot, and then sends joint position targets. This repo addresses many shortcomings with a lot of other solutions
- Web app
  - I've seen at least three other projects that use the Vuer python library to host the web interface, and this is easy to set up, but we found that the video streaming had significant latency and if we wanted to display a 3D model of the robot overlaid onto your arms in VR, that it was really laggy. Also, other projects recommend you use `ngrok` or similar service to upgrade the local http interface to https so the VR headset will let you connect, which adds more complication and latency. Our application includes an HTTPS proxy that runs with the frontend, so no sending traffic over the internet and stuff. You could put ngrok in front of this to forward traffic to internet but it's not necessary.
- Inverse kinematics
  - When setting up this project I tried a lot of inverse kinematics libraries but literally none of them worked on the kbot arms. I'm not sure why and it seems like it could've been a skill issue on my part. The solution I ended up arriving at was just doing it from scratch with jax autograd. This not only worked but allowed me to easily tweak things and add some constraints via penalty terms in the optimizer.

Teleop has been done a whopping _5_ times at K-Scale Labs before this project. In chronological order
- https://github.com/kscalelabs/arm-teleop
- https://github.com/kscalelabs/teleop-old
- https://github.com/kscalelabs/teleop_vaishak_repo_temp
- https://github.com/kscalelabs/kbotv2_teleop
- https://github.com/kscalelabs/kteleop

I reused pretty much none of the code from these
- K-OS, the interface layer with the joints from before, is being deprecated, and also doesn't support sending upper body commands at the same time we are running a locomotion policy for balance or movement
- A lot of them used Vuer, which we ditched for performance reasons mentioned above
- Some of them use pybullet for inverse kinematics, which I actually didn't try. I think this probably would've been the next thing I tried if rolling my own with jax didn't work, and I would've done this sooner if I didn't want the learning experience of digging into the lower-level details.
- Some of them just used a puppet to get the joint angles directly.

## Recommended Future work
1. Record camera feed while teleoping in sync with joint-space actions
2. Take advantage of both cameras in the headset view by doing extrinsics calibration and stereo rectification. I already did some work on this here: https://github.com/EricPedley/erics_cameras/blob/main/src/erics_cameras/scripts/calibrate_stereo.py. Right now that file works with a usb stereo camera that returns 2560x720 images. I think we should switch to these kinds of camera for k-bot instead of using CSI cameras for multiple reasons
    - They can be used on any platform, as opposed to CSI cameras which will only work on _one_ of the dev boards (rpi, vim4, jetson). This means they can also be plugged into a laptop or desktop to do calibration.
    - The vim4 camera compatibility work seems to have been a massive time sink so far and any future work on that can just be avoided by using a usb camera
    - The images are synchronized. We haven't gotten far enough with custom stereo with the two csi cameras to determine if this is really gonna be a problem, but using a USB stereo camera pair just eliminates this being a possbile problem.

    The only downside is cost but it isn't that much more, especially for the outsized utility they provide and considering the cost of the cameras relative to the total BOM. A good stereo camera (1080p 60fps x2) is like $100.
3. Control the velocity and torso angle commands with the controller joysticks
4. Use the buttons on the controllers to start/stop episodes of data recording