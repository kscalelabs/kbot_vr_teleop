import json
import numpy as np
import os
import time
from pathlib import Path
from scipy.spatial.transform import Rotation
from kscale_vr_teleop.util import fast_mat_inv
from kscale_vr_teleop.teleop_core import TeleopCore

from kscale_vr_teleop.finger_udp_server import FingerUDPHandler

import rerun as rr
from dotenv import load_dotenv
from livekit import rtc, api as lk
import asyncio

os.environ["RERUN_EXECUTABLE"] = r"C:\Program Files\Rerun\rerun.exe"
RERUN_AVAILABLE = True


kbot_vuer_to_urdf_frame = np.eye(4, dtype=np.float32)
kbot_vuer_to_urdf_frame[:3,:3] = np.array([[0,0,-1],[-1,0,0],[0,1,0]], dtype=np.float32)

hand_vuer_to_urdf_frame = np.eye(4, dtype=np.float32)
hand_vuer_to_urdf_frame[:3,:3] = np.array([[0,1,0],[0,0,1],[1,0,0]], dtype=np.float32)

# Rerun visualization setup
VISUALIZE = bool(os.environ.get("VISUALIZE", True)) and RERUN_AVAILABLE

if VISUALIZE:
    # Initialize Rerun
    logs_folder = Path(f'~/.vr_teleop_logs/{time.strftime("%Y-%m-%d")}/').expanduser()
    logs_folder.mkdir(parents=True, exist_ok=True)
    logs_path = logs_folder / f'{time.strftime("%H-%M-%S")}.rrd'

    rr.init("vr_teleop_hand")

    print("Saving logs to", logs_path)
    rr.save(logs_path)
    rr.spawn()
    
    # Set up coordinate system
    rr.log('origin_axes', rr.Transform3D(translation=[0,0,0], axis_length=0.1), static=True)
    
    # Set up timeseries plot for gripper positions with proper entity path hierarchy
    rr.log("plots/gripper_positions", rr.SeriesLines(colors=[255, 0, 0], names="Right Gripper"), static=True)
    rr.log("plots/gripper_positions", rr.SeriesLines(colors=[0, 0, 255], names="Left Gripper"), static=True)
    
    print("Rerun kinematics visualization initialized")
else:
    urdf_logger = None
    if not RERUN_AVAILABLE:
        print("Rerun visualization disabled - missing dependencies")

class TrackingHandler:
    def __init__(self, websocket, udp_host, udp_port=10000):
        print("udp_host: ", udp_host)
        self.udp_host = udp_host
        self.udp_port = udp_port

        self.teleop_core = TeleopCore(websocket, udp_host, udp_port)
        self.finger_server = FingerUDPHandler(udp_host=udp_host, udp_port=10001)

   # Setup livekit connection
        load_dotenv('env.env')

        self.LIVEKIT_API_KEY: str = os.getenv("LIVEKIT_API_KEY")
        self.LIVEKIT_API_SECRET: str = os.getenv("LIVEKIT_API_SECRET")
        self.LIVEKIT_URL: str = os.getenv("LIVEKIT_URL")
        self.LIVEKIT_ROOM_NAME: str = os.getenv('ROOM_NAME', 'pan-tilt-controls')
        # get token
    
        missing = [k for k, v in {
                "LIVEKIT_API_KEY": self.LIVEKIT_API_KEY,
                "LIVEKIT_API_SECRET": self.LIVEKIT_API_SECRET,
                "LIVEKIT_URL": self.LIVEKIT_URL
            }.items() if not v]
        if missing:
            raise RuntimeError(f"Missing env: {', '.join(missing)}")

        self.teleop_core = TeleopCore(websocket, udp_host, udp_port)
        self.finger_server = FingerUDPHandler(udp_host=udp_host, udp_port=10002)

        self.room: rtc.Room | None = None

        
    async def init_livekit(self, identity: str="vr_sender"):
        """Connect once; call after creating handler"""
        if self.room is not None:
            return
        
        # Build token with new API
        token = (
            lk.AccessToken(self.LIVEKIT_API_KEY, self.LIVEKIT_API_SECRET)
            .with_identity(identity)
            .with_grants(
                lk.VideoGrants(
                    room_join=True,
                    room=self.LIVEKIT_ROOM_NAME,
                    can_publish_data=True,
                    can_subscribe=True,
                )
            )
            .to_jwt()
        )

        # Connect RTC
        self.room = rtc.Room()

        @self.room.on("connected")
        def _on_connected():
            print(f"[LiveKit] connected as {identity} to room '{self.LIVEKIT_ROOM_NAME}' at {self.LIVEKIT_URL}")

        @self.room.on("disconnected")
        def _on_disconnected():
            print("[LiveKit] disconnected")

        @self.room.on("connection_state_changed")
        def _on_state(state):
            print(f"[LiveKit] state -> {state}")

        await self.room.connect(self.LIVEKIT_URL, token)
    async def send_livekit_data(self, data, reliable=True):
        if not self.room:
            raise RuntimeError("LiveKit room not connected; call await init_livekit() first")
        
        await self.room.local_participant.publish_data(
                json.dumps(data).encode("utf-8"),
                reliable=reliable,
            )
        
    async def handle_hand_tracking(self,event):
        print(event.keys())

        if event.get('left') != None:
            left_mat_raw = event['left']
            if isinstance(left_mat_raw, dict):
                left_controller = left_mat_raw
                left_controller = event['left']
                
                # Extract position and orientation
                position = np.array(left_controller['position'], dtype=np.float32)
                orientation = np.array(left_controller['orientation'], dtype=np.float32)  # [qx, qy, qz, qw]
                
                # Convert quaternion to rotation matrix
                qx, qy, qz, qw = orientation
                left_rotation = Rotation.from_euler('z', 90, degrees=True)
                rotation_matrix = (Rotation.from_quat([qx, qy, qz, qw], scalar_first=False)*left_rotation).as_matrix()

                # Create 4x4 transform matrix
                left_controller_matrix = np.eye(4, dtype=np.float32)
                left_controller_matrix[:3, :3] = rotation_matrix
                left_controller_matrix[:3, 3] = position
                
                # Apply frame transformation
                left_controller_pose = kbot_vuer_to_urdf_frame @ left_controller_matrix
                left_controller_pose[:3, 3] -= self.teleop_core.head_matrix[:3, 3]
                
                # Get gripper value from trigger (prefer trigger over grip for now)
                gripper_value = left_controller.get('trigger', 0.0)
                # Update controller state
                self.teleop_core.update_left_controller(left_controller_pose, gripper_value)
            else:
                left_mat_numpy = np.array(left_mat_raw, dtype=np.float32).reshape(25,4,4).transpose((0,2,1))
                wrist_mat = kbot_vuer_to_urdf_frame @ left_mat_numpy[0]
                finger_poses = (hand_vuer_to_urdf_frame @ fast_mat_inv(left_mat_numpy[0]) @ left_mat_numpy[1:].T).T
                self.teleop_core.update_left_hand(wrist_mat, finger_poses)

        # Right hand
        if event.get('right') != None:
            right_mat_raw = event['right']
            if isinstance(right_mat_raw, dict):
                right_controller = right_mat_raw
                right_controller = event['right']
                
                # Extract position and orientation
                position = np.array(right_controller['position'], dtype=np.float32)
                orientation = np.array(right_controller['orientation'], dtype=np.float32)  # [qx, qy, qz, qw]
                if (len(orientation) == 0 or len(position) == 0 ):
                    return
                # Convert quaternion to rotation matrix
                qx, qy, qz, qw = orientation
                right_rotation = Rotation.from_euler('z', -90, degrees=True)
                rotation_matrix = (Rotation.from_quat([qx, qy, qz, qw], scalar_first=False)*right_rotation).as_matrix()
                
                # Create 4x4 transform matrix
                right_controller_matrix = np.eye(4, dtype=np.float32)
                right_controller_matrix[:3, :3] = rotation_matrix
                right_controller_matrix[:3, 3] = position
                
                # Apply frame transformation
                right_controller_pose = kbot_vuer_to_urdf_frame @ right_controller_matrix
                right_controller_pose[:3, 3] -= self.teleop_core.head_matrix[:3, 3]
                
                # Get gripper value from trigger (prefer trigger over grip for now)
                gripper_value = right_controller.get('trigger', 0.0)
                
                # Update controller state
                self.teleop_core.update_right_controller(right_controller_pose, gripper_value)
            else:
                right_mat_numpy = np.array(right_mat_raw, dtype=np.float32).reshape(25,4,4).transpose((0,2,1))
                wrist_mat = kbot_vuer_to_urdf_frame @ right_mat_numpy[0]
                finger_poses = (hand_vuer_to_urdf_frame @ fast_mat_inv(right_mat_numpy[0]) @ right_mat_numpy[1:].T).T
                self.teleop_core.update_right_hand(wrist_mat, finger_poses)



        # Head
        if event.get('head') != None:
            head = event['head']
            pitch = float(head["pitch"])
            yaw = float(head["yaw"])
            matrix = np.array(head['head_matrix'], dtype=np.float32).reshape(4,4).T
            print("Head pitch, yaw:", pitch, yaw)
            print("Head matrix:", matrix)

            # Fire-and-forget publish (since this method isn't async)
            if pitch is not None and yaw is not None:
                async def _send():
                    try:
                        await self.send_livekit_data(
                            {"command": "set", "pitch": pitch, "yaw": yaw},
                            reliable=False
                        )
                    except Exception as e:
                        print(f"LiveKit send error: {e}")

                asyncio.create_task(_send())

        right_arm_joints, left_arm_joints, right_finger_angles, left_finger_angles = await self.teleop_core.compute_joint_angles()
        self.teleop_core.log_joint_angles(right_arm_joints, left_arm_joints)

        self.teleop_core.send_kinfer_commands(right_arm_joints, left_arm_joints)

        # Send finger commands via new UDP server
        self.finger_server.send_finger_commands(right_finger_angles, left_finger_angles)
