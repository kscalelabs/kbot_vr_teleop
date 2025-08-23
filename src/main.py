from vuer import Vuer, VuerSession
import asyncio
from vuer.schemas import ImageBackground, Hands
from pathlib import Path
import numpy as np
from camera_stream import CameraStreamer
from arm_inverse_kinematics import calculate_arm_joints
from hand_inverse_kinematics import calculate_hand_joints
from udp_conn import UDPHandler
from scipy.spatial.transform import Rotation
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
UDP_HOST = "127.0.0.1"  # change if needed
UDP_PORT = 8888

class VRTeleopApp:
    def __init__(self):
        self.app = Vuer(static_root=Path(__file__).parent / "assets")
        self.head_matrix = np.eye(4, dtype=np.float32)
        self.right_finger_poses = np.zeros((24, 4, 4), dtype=np.float32)
        self.left_finger_poses = np.zeros((24, 4, 4), dtype=np.float32)
        self.right_wrist_pose = np.zeros((4, 4), dtype=np.float32)
        self.left_wrist_pose = np.zeros((4, 4), dtype=np.float32)
        self.wrist_index = 0
        self.udp_handler = UDPHandler(UDP_HOST, UDP_PORT)

        self.left_arm_joints = np.zeros(5)
        self.right_arm_joints = np.zeros(5)
        self.streamer = CameraStreamer(self.app.session)

        @self.app.add_handler("CAMERA_MOVE")
        async def on_cam_move(event, session):
            head_matrix_shared = np.array(event.value["camera"]["matrix"], dtype=np.float32).reshape(4, 4)
            self.head_matrix[:] = kbot_vuer_to_urdf_frame @ head_matrix_shared.T

        @self.app.add_handler("HAND_MOVE")
        async def hand_move_handler(event, session):
            global left_hand_shared, left_landmarks_shared, prev_joint_angles
            """Handle hand tracking data and print information"""
            if event.key == 'hands':
                if 'leftState' in event.value and event.value['leftState']: # There is also more info in these but we ignore it
                    left_mat_raw = event.value['left'] # 400-long float array, 25 4x4 matrices
                    left_mat_numpy = np.array(left_mat_raw, dtype=np.float32).reshape(25, 4, 4)
                    self.left_wrist_pose = kbot_vuer_to_urdf_frame @ left_mat_numpy[0]
                    self.left_finger_poses[:] = (hand_vuer_to_urdf_frame @ fast_mat_inv(left_mat_numpy[0]) @ left_mat_numpy[1:].T).T # Make the wrist the origin

                if 'rightState' in event.value and event.value['rightState']:
                    right_mat_raw = event.value['right']
                    right_mat_numpy = np.array(right_mat_raw, dtype=np.float32).reshape(25, 4, 4).transpose((0,2,1))
                    self.right_wrist_pose = kbot_vuer_to_urdf_frame @ right_mat_numpy[0]
                    self.right_finger_poses[:] = (hand_vuer_to_urdf_frame @ fast_mat_inv(right_mat_numpy[0]) @ right_mat_numpy[1:].T).T # Make the wrist the origin
            # print(self.right_finger_poses[8,:3, 0], self.right_finger_poses[8,:3, 3])

        @self.app.spawn(start=True)
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

            while True:
                # right_arm_joints, left_arm_joints = calculate_arm_joints(self.head_matrix, self.left_hand_poses[0], self.right_hand_poses[0])
                # right_finger_joints, left_finger_joints = calculate_hand_joints(self.left_hand_poses, self.right_hand_poses)
                left_arm_joints, right_arm_joints = calculate_arm_joints(self.head_matrix, self.left_wrist_pose, self.right_wrist_pose)
                left_finger_joints, right_finger_joints = calculate_hand_joints(self.left_finger_poses, self.right_finger_poses)
                self.udp_handler._send_udp(right_arm_joints, left_arm_joints, right_finger_joints, left_finger_joints)
                self.streamer.update_stream()

if __name__ == "__main__":
    app = VRTeleopApp()
