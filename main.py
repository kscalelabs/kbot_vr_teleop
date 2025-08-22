from vuer import Vuer, VuerSession
import asyncio
from vuer.schemas import ImageBackground, Hands
from pathlib import Path
import numpy as np
from .camera_stream import stream_cameras
from .arm_inverse_kinematics import calculate_arm_joints
from .udp_conn import UDPHandler
from scipy.spatial.transform import Rotation


vuer_to_urdf_frame = np.eye(4, dtype=np.float32)
vuer_to_urdf_frame[:3,:3] = Rotation.from_euler('xz', (90, 90), degrees=True).as_matrix()

UDP_HOST = "127.0.0.1"  # change if needed
UDP_PORT = 8888

class VRTeleopApp:
    def __init__(self):
        self.app = Vuer(static_root=Path(__file__).parent / "assets")
        self.head_matrix = np.eye(4, dtype=np.float32)
        self.right_hand_poses = np.zeros((25, 4, 4), dtype=np.float32)
        self.left_hand_poses = np.zeros((25, 4, 4), dtype=np.float32)
        self.wrist_index = 0
        self.udp_handler = UDPHandler(UDP_HOST, UDP_PORT)

        @self.app.add_handler("CAMERA_MOVE")
        async def on_cam_move(event, session):
            head_matrix_shared = np.array(event.value["camera"]["matrix"], dtype=np.float32).reshape(4, 4)
            self.head_matrix[:] = head_matrix_shared.T @ vuer_to_urdf_frame

        @self.app.add_handler("HAND_MOVE")
        async def hand_move_handler(event, session):
            global left_hand_shared, left_landmarks_shared, prev_joint_angles
            """Handle hand tracking data and print information"""
            if event.key == 'hands':
                if 'leftState' in event.value and event.value['leftState']: # There is also more info in these but we ignore it
                    left_mat_raw = event.value['left'] # 400-long float array, 25 4x4 matrices
                    left_mat_numpy = np.array(left_mat_raw, dtype=np.float32).reshape(25, 4, 4)
                    self.left_hand_poses[:] = left_mat_numpy[0].T @ vuer_to_urdf_frame # Use the first matrix as the hand pose

                if 'rightState' in event.value and event.value['rightState']:
                    right_mat_raw = event.value['right']
                    right_mat_numpy = np.array(right_mat_raw, dtype=np.float32).reshape(25, 4, 4)
                    self.right_hand_poses[:] = right_mat_numpy[0].T @ vuer_to_urdf_frame # Use the first matrix as the hand pose
            right_arm_joints, left_arm_joints = calculate_arm_joints(self.left_hand_poses[0], self.right_hand_poses[0])
            right_finger_joints, left_finger_joints = calculate_arm_joints(self.left_hand_poses, self.right_hand_poses)
            self.udp_handler._send_udp(right_arm_joints, left_arm_joints, right_finger_joints, left_finger_joints)

        @self.app.spawn(start=True)
        async def main(session: VuerSession):
            session.upsert(
                Hands(
                    stream=True,
                    key="hands",
                    hideLeft=False,       # hides the hand, but still streams the data.
                    hideRight=False,      # hides the hand, but still streams the data.
                    # disableLeft=False,    # disables the left data stream, also hides the hand.
                    # disableRight=False,   # disables the right data stream, also hides the hand.
                ),
                to="bgChildren",
            )

            await stream_cameras(session)

if __name__ == "__main__":
    app = VRTeleopApp()
