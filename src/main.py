
import cv2
from vuer import Vuer, VuerSession
import asyncio
from vuer.schemas import ImageBackground, Hands
import numpy as np
from erics_cameras.libcamera_cam import LibCameraCam
from arm_inverse_kinematics import calculate_arm_joints
from hand_inverse_kinematics import calculate_hand_joints
from udp_conn import UDPHandler
from util import fast_mat_inv

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
UDP_HOST = "10.33.13.62"  # change if needed
UDP_PORT = 8888

cam_mat = np.array([[266.61728276,0.,643.83126137],[0.,266.94450686,494.81811813],[0.,0.,1.,]])
dist_coeffs = np.array([[-6.07417419e-02,9.95447444e-02,-2.26448001e-04,1.22881804e-03,3.42134205e-03,1.45361886e-01,8.03248099e-02,2.11170107e-02,-3.80620047e-03,2.48350591e-05,-8.33565666e-04,2.97806723e-05]])

head_matrix = np.eye(4, dtype=np.float32)
right_finger_poses = np.zeros((24, 4, 4), dtype=np.float32)
left_finger_poses = np.zeros((24, 4, 4), dtype=np.float32)
right_wrist_pose = np.zeros((4, 4), dtype=np.float32)
left_wrist_pose = np.zeros((4, 4), dtype=np.float32)
wrist_index = 0
udp_handler = UDPHandler(UDP_HOST, UDP_PORT)

left_arm_joints = np.zeros(5)
right_arm_joints = np.zeros(5)

STREAM = False

async def stream_cameras(session: VuerSession, left_src=0, right_src=1):
    if STREAM:
        left_pipeline = "libcamerasrc camera-name=/base/axi/pcie@1000120000/rp1/i2c@80000/ov5647@36 exposure-time-mode=0 analogue-gain-mode=0 ae-enable=true awb-enable=true af-mode=manual ! video/x-raw,format=BGR,width=1280,height=720,framerate=30/1 ! videoconvert ! appsink drop=1 max-buffers=1"
        right_pipeline = "libcamerasrc camera-name=/base/axi/pcie@1000120000/rp1/i2c@88000/ov5647@36 exposure-time-mode=0 analogue-gain-mode=0 ae-enable=true awb-enable=true af-mode=manual ! video/x-raw,format=BGR,width=1280,height=720,framerate=30/1 ! videoconvert ! appsink drop=1 max-buffers=1"
        cam_left = cv2.VideoCapture(left_pipeline, cv2.CAP_GSTREAMER)
        cam_right = cv2.VideoCapture(right_pipeline, cv2.CAP_GSTREAMER)
    
    while True:
        left_arm_joints, right_arm_joints = calculate_arm_joints(head_matrix, left_wrist_pose, right_wrist_pose)
        left_finger_joints, right_finger_joints = calculate_hand_joints(left_finger_poses, right_finger_poses)
        udp_handler._send_udp(right_arm_joints, left_arm_joints, right_finger_joints, left_finger_joints)
        if STREAM:
            ret_left, frame_left = cam_left.read()
            ret_right, frame_right = cam_right.read()
            if not ret_left or not ret_right:
                continue
            frame_left_rgb = cv2.cvtColor(frame_left, cv2.COLOR_BGR2RGB)
            # frame_right_rgb = cv2.cvtColor(frame_right, cv2.COLOR_BGR2RGB)
            frame_left_rgb = cv2.undistort(frame_left_rgb, cam_mat, dist_coeffs)
            frame_left_rgb = cv2.resize(frame_left_rgb, (640, 360), interpolation=cv2.INTER_LINEAR)
            frame_right_rgb = frame_left_rgb.copy()
            # frame_right_rgb = cv2.undistort(frame_right_rgb, cam_mat, dist_coeffs)
            # Add text labels for left/right cameras
            # cv2.putText(frame_left_rgb, "Left Camera", (600, 30), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 4)
            # cv2.putText(frame_right_rgb, "Right Camera", (600, 30), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 4)
            # Send both images as ImageBackground objects for left/right eye
            interpupilary_dist = 0

            distance_to_camera = 3.5*cam_mat[0][0] / frame_left_rgb.shape[1] # TODO: remove this hard-coded 2 multiplier
            vertical_angle_rad = np.deg2rad(25)  # Example vertical angle, adjust as needed
            # Calculate positions for left and right screens with vertical displacement
            # Keep the same distance from user but move down by the vertical angle
            y_offset = -distance_to_camera * np.sin(vertical_angle_rad)  # Negative for below horizon
            z_offset = distance_to_camera * (np.cos(vertical_angle_rad) - 1)  # Adjustment to maintain distance
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

    @app.add_handler("HAND_MOVE")
    async def hand_move_handler(event, session):
        global left_wrist_pose, right_wrist_pose, left_finger_poses, right_finger_poses
        """Handle hand tracking data and print information"""
        if event.key == 'hands':
            if 'leftState' in event.value and event.value['leftState']: # There is also more info in these but we ignore it
                left_mat_raw = event.value['left'] # 400-long float array, 25 4x4 matrices
                left_mat_numpy = np.array(left_mat_raw, dtype=np.float32).reshape(25, 4, 4)
                left_wrist_pose[:] = kbot_vuer_to_urdf_frame @ left_mat_numpy[0]
                left_finger_poses[:] = (hand_vuer_to_urdf_frame @ fast_mat_inv(left_mat_numpy[0]) @ left_mat_numpy[1:].T).T # Make the wrist the origin

            if 'rightState' in event.value and event.value['rightState']:
                right_mat_raw = event.value['right']
                right_mat_numpy = np.array(right_mat_raw, dtype=np.float32).reshape(25, 4, 4).transpose((0,2,1))
                right_wrist_pose[:] = kbot_vuer_to_urdf_frame @ right_mat_numpy[0]
                right_finger_poses[:] = (hand_vuer_to_urdf_frame @ fast_mat_inv(right_mat_numpy[0]) @ right_mat_numpy[1:].T).T # Make the wrist the origin
        # print(right_finger_poses[8,:3, 0], right_finger_poses[8,:3, 3])
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
