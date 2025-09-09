import json
import numpy as np
import os
import time
from pathlib import Path
from kscale_vr_teleop.util import fast_mat_inv
from kscale_vr_teleop.teleop_core import TeleopCore

import rerun as rr
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

    rr.init("vr_teleop")

    print("Saving logs to", logs_path)
    rr.save(logs_path)
    rr.spawn()
    
    # Set up coordinate system
    rr.log('origin_axes', rr.Transform3D(translation=[0,0,0], axis_length=0.1), static=True)
    print("Rerun kinematics visualization initialized")
else:
    urdf_logger = None
    if not RERUN_AVAILABLE:
        print("Rerun visualization disabled - missing dependencies")

class HandTrackingHandler:
    def __init__(self, udp_host='localhost', udp_port=10000):
        self.udp_host = udp_host
        self.udp_port = udp_port

        self.teleop_core = TeleopCore(udp_host, udp_port)

    def handle_hand_tracking(self,event):
        if event.get('left') != None:
            left_mat_raw = event['left']
            left_mat_numpy = np.array(left_mat_raw, dtype=np.float32).reshape(25,4,4).transpose((0,2,1))
            self.teleop_core.left_wrist_pose[:] = kbot_vuer_to_urdf_frame @ left_mat_numpy[0]
            self.teleop_core.left_wrist_pose[:3,3] -= self.teleop_core.head_matrix[:3,3]
            self.teleop_core.left_finger_poses[:] = (hand_vuer_to_urdf_frame @ fast_mat_inv(left_mat_numpy[0]) @ left_mat_numpy[1:].T).T

        # Right hand
        if event.get('right') != None:
            right_mat_raw = event['right']
            right_mat_numpy = np.array(right_mat_raw, dtype=np.float32).reshape(25,4,4).transpose((0,2,1))
            self.teleop_core.right_wrist_pose[:] = kbot_vuer_to_urdf_frame @ right_mat_numpy[0]
            self.teleop_core.right_wrist_pose[:3,3] -= self.teleop_core.head_matrix[:3,3]
            self.teleop_core.right_finger_poses[:] = (hand_vuer_to_urdf_frame @ fast_mat_inv(right_mat_numpy[0]) @ right_mat_numpy[1:].T).T

        right_arm_joints, left_arm_joints = self.teleop_core.compute_joint_angles()
        self.teleop_core.log_joint_angles(right_arm_joints, left_arm_joints)

        self.teleop_core.send_kinfer_commands(right_arm_joints, left_arm_joints)