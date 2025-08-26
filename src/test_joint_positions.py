import cv2
from vuer import Vuer, VuerSession
import asyncio
from vuer.schemas import ImageBackground, Hands
import numpy as np
from erics_cameras.libcamera_cam import LibCameraCam
from arm_inverse_kinematics import calculate_arm_joints, arms_robot, right_arm_links
from udp_conn import UDPHandler
import rerun as rr

UDP_HOST = "10.33.13.62"  # change if needed
UDP_PORT = 8888
rr.init("vr_teleop", spawn=True)
udp_handler = UDPHandler(UDP_HOST, UDP_PORT)

rr.log('origin_axes', rr.Transform3D(translation=[0,0,0], axis_length=0.1), static=True)

while True:
    right_arm_joints = np.array([-np.pi/4, np.pi/4,0,0,0])
    udp_handler._send_udp(right_arm_joints, np.zeros(5), np.zeros(6), np.zeros(6))

    new_config = {k.name: right_arm_joints[i] for i, k in enumerate(arms_robot.actuated_joints[::2])}
    arms_robot.update_cfg(new_config)
    positions = [arms_robot.get_transform(link, 'base')[:3,3] for link in right_arm_links]
    rr.log('kinematic_chain', rr.LineStrips3D(positions, colors=[[255,255,255]]*(len(positions)-1), radii=0.005))