import cv2
from vuer import Vuer, VuerSession
import asyncio
from vuer.schemas import ImageBackground, Hands
import numpy as np
from erics_cameras.libcamera_cam import LibCameraCam
from kscale_vr_teleop.hand_inverse_kinematics import calculate_hand_joints_no_ik
from kscale_vr_teleop.udp_conn import UDPHandler, RLUDPHandler
from kscale_vr_teleop.util import fast_mat_inv
from scipy.spatial.transform import Rotation
import time
from kscale_vr_teleop.analysis.rerun_loader_urdf import URDFLogger
import os

from kscale_vr_teleop.jax_ik import RobotInverseKinematics
from kscale_vr_teleop._assets import ASSETS_DIR

urdf_path  = str(ASSETS_DIR / "kbot" / "robot.urdf")

SEND_EE_CONTROL = False
VISUALIZE = bool(os.environ.get("VISUALIZE", False))
UDP_HOST = "127.0.0.1"  # change if needed

urdf_logger = URDFLogger(urdf_path)

import rerun as rr

rr.init("vr_teleop", spawn=True)

rr.log('origin_axes', rr.Transform3D(translation=[0,0,0], axis_length=0.1), static=True)
kbot_vuer_to_urdf_frame = np.eye(4, dtype=np.float32)
kbot_vuer_to_urdf_frame[:3,:3] = np.array([
    [0, 0, -1],
    [-1, 0, 0],
    [0, 1, 0]
], dtype=np.float32)

hand_vuer_to_urdf_frame = np.eye(4, dtype=np.float32)
hand_vuer_to_urdf_frame[:3,:3] = np.array([
    [0, 1, 0],
    [0, 0, 1],
    [1, 0, 0]
], dtype=np.float32)

cam_mat = np.array([[266.61728276,0.,643.83126137],[0.,266.94450686,494.81811813],[0.,0.,1.,]])
dist_coeffs = np.array([[-6.07417419e-02,9.95447444e-02,-2.26448001e-04,1.22881804e-03,3.42134205e-03,1.45361886e-01,8.03248099e-02,2.11170107e-02,-3.80620047e-03,2.48350591e-05,-8.33565666e-04,2.97806723e-05]])

head_matrix = np.eye(4, dtype=np.float32)
right_finger_poses = np.zeros((24, 4, 4), dtype=np.float32)
left_finger_poses = np.zeros((24, 4, 4), dtype=np.float32)
right_wrist_pose = np.zeros((4, 4), dtype=np.float32)
left_wrist_pose = np.zeros((4, 4), dtype=np.float32)
wrist_index = 0
if SEND_EE_CONTROL:
    udp_handler = RLUDPHandler(UDP_HOST)
else:
    udp_handler = UDPHandler(UDP_HOST, 8888)

left_arm_joints = np.zeros(5)
right_arm_joints = np.zeros(5)

STREAM = bool(os.environ.get("STREAM", False))

base_to_head_transform = np.eye(4)
base_to_head_transform[:3,3] = np.array([
	0, 0, 0.25
])

ik_solver = RobotInverseKinematics(urdf_path, ['KB_C_501X_Right_Bayonet_Adapter_Hard_Stop', 'KB_C_501X_Left_Bayonet_Adapter_Hard_Stop'], 'base')

async def stream_cameras(session: VuerSession, left_src=0, right_src=1):
    if STREAM:
        left_pipeline = "libcamerasrc camera-name=/base/axi/pcie@1000120000/rp1/i2c@80000/ov5647@36 exposure-time-mode=0 analogue-gain-mode=0 ae-enable=true awb-enable=true af-mode=manual ! video/x-raw,format=BGR,width=1280,height=720,framerate=30/1 ! videoconvert ! appsink drop=1 max-buffers=1"
        right_pipeline = "libcamerasrc camera-name=/base/axi/pcie@1000120000/rp1/i2c@88000/ov5647@36 exposure-time-mode=0 analogue-gain-mode=0 ae-enable=true awb-enable=true af-mode=manual ! video/x-raw,format=BGR,width=1280,height=720,framerate=30/1 ! videoconvert ! appsink drop=1 max-buffers=1"
        cam_left = cv2.VideoCapture(left_pipeline, cv2.CAP_GSTREAMER)
        cam_right = cv2.VideoCapture(right_pipeline, cv2.CAP_GSTREAMER)
        # cam_left = cv2.VideoCapture('udp://@127.0.0.1:8554?buffer_size=65535&pkt_size=65535&fifo_size=65535')
    
    while True:
        hand_target_left = base_to_head_transform @ left_wrist_pose
        hand_target_right = base_to_head_transform @ right_wrist_pose
        rr.log('hand_target_left', rr.Transform3D(translation=hand_target_left[:3, 3], mat3x3=hand_target_left[:3, :3], axis_length=0.05))
        rr.log('hand_target_right', rr.Transform3D(translation=hand_target_right[:3, 3], mat3x3=hand_target_right[:3, :3], axis_length=0.05))
        # left_arm_joints, right_arm_joints = calculate_arm_joints(head_matrix, hand_target_left, hand_target_right)

        joints = ik_solver.inverse_kinematics(np.array([hand_target_right, hand_target_left]))
        left_arm_joints = joints[1::2]
        right_arm_joints = joints[::2]
        left_finger_joints, right_finger_joints = calculate_hand_joints_no_ik(left_finger_poses, right_finger_poses)
        if SEND_EE_CONTROL:
            udp_handler._send_udp(hand_target_left, hand_target_right)
        else:
            udp_handler._send_udp(right_arm_joints, left_arm_joints, right_finger_joints, left_finger_joints)

        if VISUALIZE:
            new_config = {k.name: right_arm_joints[i] for i, k in enumerate(ik_solver.active_joints[::2])}
            new_config.update({k.name: left_arm_joints[i] for i, k in enumerate(ik_solver.active_joints[1::2])})
            urdf_logger.log(new_config)
        if STREAM:
            ret_left, frame_left = cam_left.read()
            if not ret_left:
                continue
            # ret_right, frame_right = cam_right.read()
            # if not ret_left or not ret_right:
            #     continue
            frame_left_rgb = cv2.cvtColor(frame_left, cv2.COLOR_BGR2RGB)
            frame_left_rgb = cv2.undistort(frame_left_rgb, cam_mat, dist_coeffs)
            frame_left_rgb = cv2.resize(frame_left_rgb, (640, 360), interpolation=cv2.INTER_LINEAR)
            frame_right_rgb = frame_left_rgb.copy()
            interpupilary_dist = 0

            distance_to_camera = 3.5*cam_mat[0][0] / frame_left_rgb.shape[1]
            vertical_angle_rad = np.deg2rad(25)
            y_offset = -distance_to_camera * np.sin(vertical_angle_rad)
            z_offset = distance_to_camera * (np.cos(vertical_angle_rad) - 1)
            session.upsert([
                ImageBackground(
                    frame_left_rgb,
                    aspect=1.778,
                    height=2,
                    distanceToCamera=distance_to_camera,
                    position=[-interpupilary_dist/2, y_offset, z_offset],
                    layers=1,
                    format="jpeg",
                    quality=1000,
                    key="background-left",
                    interpolate=True,
                ),
                ImageBackground(
                    frame_right_rgb,
                    aspect=1.778,
                    height=2,
                    distanceToCamera=distance_to_camera,
                    position=[-interpupilary_dist/2, y_offset, z_offset],
                    layers=2,
                    format="jpeg",
                    quality=1000,
                    key="background-right",
                    interpolate=True,
                ),
            ], to="bgChildren")
        await asyncio.sleep(1/30)  # ~30 FPS for smoother streaming


if __name__ == "__main__":
    app = Vuer()

    @app.add_handler("CAMERA_MOVE")
    async def on_cam_move(event, session):
        head_matrix_shared = np.array(event.value["camera"]["matrix"], dtype=np.float32).reshape(4, 4)
        head_matrix[:] = kbot_vuer_to_urdf_frame @ head_matrix_shared.T
        rr.log('head', rr.Transform3D(translation=np.zeros(3), mat3x3=head_matrix[:3, :3], axis_length=0.05))

    @app.add_handler("HAND_MOVE")
    async def hand_move_handler(event, session):
        global left_wrist_pose, right_wrist_pose, left_finger_poses, right_finger_poses
        if event.key == 'hands':
            if 'leftState' in event.value and event.value['leftState']:
                left_mat_raw = event.value['left']
                left_mat_numpy = np.array(left_mat_raw, dtype=np.float32).reshape(25, 4, 4).transpose((0,2,1))
                left_wrist_pose[:] = kbot_vuer_to_urdf_frame @ left_mat_numpy[0]
                left_wrist_pose[:3, 3] -= head_matrix[:3, 3]
                left_finger_poses[:] = (hand_vuer_to_urdf_frame @ fast_mat_inv(left_mat_numpy[0]) @ left_mat_numpy[1:].T).T
                rr.log('left_wrist', rr.Transform3D(translation=left_wrist_pose[:3, 3], mat3x3=left_wrist_pose[:3, :3], axis_length=0.05))

            if 'rightState' in event.value and event.value['rightState']:
                right_mat_raw = event.value['right']
                right_mat_numpy = np.array(right_mat_raw, dtype=np.float32).reshape(25, 4, 4).transpose((0,2,1))
                right_wrist_pose[:] = kbot_vuer_to_urdf_frame @ right_mat_numpy[0]
                right_wrist_pose[:3, 3] -= head_matrix[:3, 3]
                right_finger_poses[:] = (hand_vuer_to_urdf_frame @ fast_mat_inv(right_mat_numpy[0]) @ right_mat_numpy[1:].T).T
                rr.log('right_wrist', rr.Transform3D(translation=right_wrist_pose[:3, 3], mat3x3=right_wrist_pose[:3, :3], axis_length=0.05))
    @app.spawn(start=True)
    async def main(session: VuerSession):
        session.upsert(
            Hands(
                stream=True,
                key="hands",
                hideLeft=False,       # hides the hand, but still streams the data.
                hideRight=False,      # hides the hand, but still streams the data.
            ),
            to="bgChildren",
        )
        await stream_cameras(session)
    app.run()
