import cv2
from vuer import Vuer, VuerSession
import asyncio
from vuer.schemas import ImageBackground, Hands
import numpy as np
from kscale_vr_teleop.hand_inverse_kinematics import calculate_hand_joints_no_ik
from kscale_vr_teleop.udp_conn import RLUDPHandler
from kscale_vr_teleop.util import fast_mat_inv
import time
from kscale_vr_teleop.analysis.rerun_loader_urdf import URDFLogger
import os

from kscale_vr_teleop.jax_ik import RobotInverseKinematics
from kscale_vr_teleop._assets import ASSETS_DIR
from kscale_vr_teleop.command_conn import Commander16
from pathlib import Path
from line_profiler import profile
import warnings

urdf_path  = str(ASSETS_DIR / "kbot_legless" / "robot.urdf")

SEND_EE_CONTROL = False
VISUALIZE = bool(os.environ.get("VISUALIZE", False))
UDP_HOST = "127.0.0.1"  # change if needed

urdf_logger = URDFLogger(urdf_path)

import rerun as rr

logs_folder = Path(f'~/.vr_teleop_logs/{time.strftime("%Y-%m-%d")}/').expanduser()
logs_folder.mkdir(parents=True, exist_ok=True)
logs_path = logs_folder / f'{time.strftime("%H-%M-%S")}.rrd'

rr.init("vr_teleop", spawn=VISUALIZE)

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
right_wrist_pose = np.eye(4,dtype=np.float32)
left_wrist_pose = np.eye(4,dtype=np.float32)
left_wrist_pose[:3,3] = np.array([0.2, 0.2, -0.4])
right_wrist_pose[:3,3] = np.array([0.2, -0.2, -0.4])
default_wrist_rotation = np.array([
    [0, 0, -1],
    [-1, 0, 0],
    [0, 1, 0]
])
left_wrist_pose[:3,:3] = default_wrist_rotation
right_wrist_pose[:3,:3] = default_wrist_rotation
wrist_index = 0
if SEND_EE_CONTROL:
    udp_handler = RLUDPHandler(UDP_HOST)
else:
    # udp_handler = UDPHandler(UDP_HOST, 8888)
    # udp_handler = KOSHandler()
    handler = Commander16()

left_arm_joints = np.zeros(5)
right_arm_joints = np.zeros(5)

STREAM = bool(os.environ.get("STREAM", False))

base_to_head_transform = np.eye(4)
base_to_head_transform[:3,3] = np.array([
	0, 0, 0.25
])

ik_solver = RobotInverseKinematics(urdf_path, ['PRT0001', 'PRT0001_2'], 'base')

@profile
async def control_arms(session: VuerSession):
    frame_count = 0
    start_time = time.time()
    last_fps_print = start_time
    while True:
        loop_start = time.time()
        frame_count += 1
        hand_target_left = base_to_head_transform @ left_wrist_pose
        hand_target_right = base_to_head_transform @ right_wrist_pose
        # clamp hand targets z coordinate to be above -0.2
        hand_target_left[2, 3] = max(hand_target_left[2, 3], -0.2)
        hand_target_right[2, 3] = max(hand_target_right[2, 3], -0.2)
        rr.log('hand_target_left', rr.Transform3D(translation=hand_target_left[:3, 3], mat3x3=hand_target_left[:3, :3], axis_length=0.05))
        rr.log('hand_target_right', rr.Transform3D(translation=hand_target_right[:3, 3], mat3x3=hand_target_right[:3, :3], axis_length=0.05))
        # left_arm_joints, right_arm_joints = calculate_arm_joints(head_matrix, hand_target_left, hand_target_right)

        joints = ik_solver.inverse_kinematics(np.array([hand_target_right, hand_target_left]))
        # Convert JAX array to NumPy for faster slicing operations
        joints = np.asarray(joints)
        actual_positions = ik_solver.forward_kinematics(joints)
        rr.log('actual_right', rr.Transform3D(translation=actual_positions[0][:3, 3], mat3x3=actual_positions[0][:3, :3], axis_length=0.1))
        rr.log('actual_left', rr.Transform3D(translation=actual_positions[1][:3, 3], mat3x3=actual_positions[1][:3, :3], axis_length=0.1))
        left_arm_joints = joints[1::2]
        right_arm_joints = joints[::2]
        right_finger_spacing = np.linalg.norm(right_finger_poses[8,:3,3] - right_finger_poses[3,:3,3])
        right_gripper_joint = np.clip(right_finger_spacing/0.15, 0, 1)
        left_finger_spacing = np.linalg.norm(left_finger_poses[8,:3,3] - left_finger_poses[3,:3,3])
        left_gripper_joint = np.clip(left_finger_spacing/0.15, 0, 1)
        if SEND_EE_CONTROL:
            udp_handler._send_udp(hand_target_left, hand_target_right)
        else:
            handler.send_commands(right_arm_joints.tolist() + [right_gripper_joint], left_arm_joints.tolist() + [left_gripper_joint])

        if VISUALIZE:
            new_config = {k.name: right_arm_joints[i] for i, k in enumerate(ik_solver.active_joints[::2])}
            new_config.update({k.name: left_arm_joints[i] for i, k in enumerate(ik_solver.active_joints[1::2])})
            urdf_logger.log(new_config)

        # Print FPS every second using carriage return for clean output
        current_time = time.time()
        if current_time - last_fps_print >= 1.0:
            fps = 1/(current_time - loop_start)
            print(f"\rFPS: {fps:.2f} | Frames: {frame_count}", end="", flush=True)
            last_fps_print = current_time

        await asyncio.sleep(1/30)  # ~30 FPS for smoother streaming

@profile
async def stream_cameras(session: VuerSession, left_src=0, right_src=1):
    if not STREAM:
        return
    left_pipeline = "libcamerasrc camera-name=/base/axi/pcie@1000120000/rp1/i2c@88000/ov5647@36 exposure-time-mode=0 analogue-gain-mode=0 ae-enable=true awb-enable=true af-mode=manual ! video/x-raw,format=BGR,width=1280,height=720,framerate=30/1 ! videoconvert ! appsink drop=1 max-buffers=1"
    # right_pipeline = "libcamerasrc camera-name=/base/axi/pcie@1000120000/rp1/i2c@88000/ov5647@36 exposure-time-mode=0 analogue-gain-mode=0 ae-enable=true awb-enable=true af-mode=manual ! video/x-raw,format=BGR,width=1280,height=720,framerate=30/1 ! videoconvert ! appsink drop=1 max-buffers=1"
    cam_left = cv2.VideoCapture(left_pipeline, cv2.CAP_GSTREAMER)
    # cam_right = cv2.VideoCapture(right_pipeline, cv2.CAP_GSTREAMER)

    new_cam_mat, _ = cv2.getOptimalNewCameraMatrix(cam_mat, dist_coeffs, (1280, 720), 1, (1280, 720))
    map_x, map_y = cv2.initUndistortRectifyMap(cam_mat, dist_coeffs, None, new_cam_mat, (1280, 720), cv2.CV_32FC1)
    # cam_left = cv2.VideoCapture('udp://@127.0.0.1:8554?buffer_size=65535&pkt_size=65535&fifo_size=65535')
    
    # FPS tracking variables
    frame_count = 0    
    failed_frames = 0

    while True:
        await asyncio.sleep(1/30)
        frame_count += 1
        ret_left, frame_left = cam_left.read()
        if not ret_left:
            warnings.warn(f"Failed to read from left camera ({failed_frames}) consecutive failures")
            failed_frames += 1
            continue
        failed_frames = 0
            # frame_left = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8) # TODO: remove
        # ret_right, frame_right = cam_right.read()
        # if not ret_left or not ret_right:
        #     continue
        frame_left_rgb = cv2.cvtColor(frame_left, cv2.COLOR_BGR2RGB)
        # frame_left_rgb = cv2.remap(frame_left_rgb, map_x, map_y, interpolation=cv2.INTER_LINEAR)
        frame_left_rgb = cv2.resize(frame_left_rgb, (640, 360), interpolation=cv2.INTER_LINEAR)
        cv2.putText(frame_left_rgb, f"Frames: {frame_count}", (10,30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
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
    try:
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
                tasks = [
                    stream_cameras(session),
                    control_arms(session)
                ]

                await asyncio.gather(*tasks)
    finally:
        print("Saving logs to", logs_path)
        rr.save(logs_path)
    app.run()
