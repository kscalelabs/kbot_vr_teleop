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
os.environ["RERUN_EXECUTABLE"] = r"C:\Program Files\Rerun\rerun.exe"
RERUN_AVAILABLE = True

kbot_xr_to_urdf_frame = np.array([
    [0,  0, -1,  0],  # Robot X-axis = -VR Z-axis (flip forward/back)
    [-1, 0,  0,  0],  # Robot Y-axis = -VR X-axis (flip left/right)
    [0,  1,  0,  0],  # Robot Z-axis = +VR Y-axis (keep up direction)
    [0,  0,  0,  1]   # Homogeneous coordinate
], dtype=np.float32)

hand_xr_to_urdf_frame = np.array([
    [0, 1, 0, 0],  # Rotate hand frame: X-axis → Y-axis
    [0, 0, 1, 0],  # Rotate hand frame: Y-axis → Z-axis
    [1, 0, 0, 0],  # Rotate hand frame: Z-axis → X-axis
    [0, 0, 0, 1]   # Homogeneous coordinate
], dtype=np.float32)

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
    def __init__(self, websocket, udp_host, urdf_logger, ik_solver=None, udp_port=10000):
        self.udp_host = udp_host
        self.udp_port = udp_port

        self.teleop_core = TeleopCore(websocket, udp_host, udp_port, urdf_logger, ik_solver)
        self.finger_server = FingerUDPHandler(udp_host=udp_host, udp_port=10001)
    
    def _handle_controller_tracking(self, controller_data, side):
        '''
        Handles controller tracking for either left or right side
        '''
         #controller tracking
        controller = controller_data
        direction = -1 if side == 'right' else 1
        # Extract position and orientation
        position = np.array(controller['position'], dtype=np.float32)
        orientation = np.array(controller['orientation'], dtype=np.float32)  # [qx, qy, qz, qw]
        
        # Convert quaternion to rotation matrix
        qx, qy, qz, qw = orientation
        rotation = Rotation.from_euler('z', 90 * direction, degrees=True)
        rotation_matrix = (Rotation.from_quat([qx, qy, qz, qw], scalar_first=False)*rotation).as_matrix()

        # Create 4x4 transform matrix
        controller_matrix = np.eye(4, dtype=np.float32)
        controller_matrix[:3, :3] = rotation_matrix
        controller_matrix[:3, 3] = position
        
        # Apply frame transformation
        controller_pose = kbot_xr_to_urdf_frame @ controller_matrix
        controller_pose[:3, 3] -= self.teleop_core.head_matrix[:3, 3]
        
        gripper_value = controller.get('trigger', 0.0)
        # Update controller state
        if side == 'left':
            self.teleop_core.update_left_controller(controller_pose, gripper_value)
        else:
            self.teleop_core.update_right_controller(controller_pose, gripper_value)

    def _handle_hand_tracking(self, hand_data, side):
        hand_mat_numpy = np.array(hand_data, dtype=np.float32).reshape(25,4,4).transpose((0,2,1))
        wrist_mat = kbot_xr_to_urdf_frame @ hand_mat_numpy[0]
        finger_poses = (hand_xr_to_urdf_frame @ fast_mat_inv(hand_mat_numpy[0]) @ hand_mat_numpy[1:].T).T
        
        if side == 'left':
            self.teleop_core.update_left_hand(wrist_mat, finger_poses)
        else:
            self.teleop_core.update_right_hand(wrist_mat, finger_poses)

    async def handle_tracking(self,event):
        '''
        Calls the correct function to update controllers or hands based on the structure of the event.
        Finally calls compute_and_send_joints
        '''
        props = ["left", "right"]
        for prop in props:
            if event.get(prop) != None:
                mat_raw = event[prop]
                if isinstance(mat_raw, dict):
                    self._handle_controller_tracking(mat_raw, prop)
                else:
                    self._handle_hand_tracking(mat_raw, prop)

        await self.teleop_core.compute_and_send_joints()

        # Send finger commands via new UDP server
        # self.finger_server.send_finger_commands(right_finger_angles, left_finger_angles)
