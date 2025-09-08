import json
import numpy as np
import os
import time
from pathlib import Path
from kscale_vr_teleop.util import fast_mat_inv
from kscale_vr_teleop.jax_ik import RobotInverseKinematics
from kscale_vr_teleop._assets import ASSETS_DIR

# Optional Rerun imports - disable visualization if not available
# try:
from kscale_vr_teleop.analysis.rerun_loader_urdf import URDFLogger
import rerun as rr
os.environ["RERUN_EXECUTABLE"] = r"C:\Program Files\Rerun\rerun.exe"
RERUN_AVAILABLE = True
# except ImportError as e:
#     print(f"Rerun visualization not available: {e}")
#     RERUN_AVAILABLE = False
#     URDFLogger = None
#     rr = None

base_to_head_transform = np.eye(4)
base_to_head_transform[:3,3] = np.array([0, 0, 0.25])

kbot_vuer_to_urdf_frame = np.eye(4, dtype=np.float32)
kbot_vuer_to_urdf_frame[:3,:3] = np.array([[0,0,-1],[-1,0,0],[0,1,0]], dtype=np.float32)

hand_vuer_to_urdf_frame = np.eye(4, dtype=np.float32)
hand_vuer_to_urdf_frame[:3,:3] = np.array([[0,1,0],[0,0,1],[1,0,0]], dtype=np.float32)

head_matrix = np.eye(4, dtype=np.float32)
right_wrist_pose = np.zeros((4,4), dtype=np.float32)
left_wrist_pose = np.zeros((4,4), dtype=np.float32)
right_finger_poses = np.zeros((24,4,4), dtype=np.float32)
left_finger_poses = np.zeros((24,4,4), dtype=np.float32)
urdf_path = str(ASSETS_DIR / "kbot_legless" / "robot.urdf")
ik_solver = RobotInverseKinematics(urdf_path, ['PRT0001', 'PRT0001_2'], 'base')

# Rerun visualization setup
VISUALIZE = bool(os.environ.get("VISUALIZE", True)) and RERUN_AVAILABLE

if VISUALIZE:
    # Initialize Rerun
    rr.init("kinematics_viz", spawn=True)
    
    # Set up logging directory
    logs_folder = Path(f'~/.kinematics_logs/{time.strftime("%Y-%m-%d")}/').expanduser()
    logs_folder.mkdir(parents=True, exist_ok=True)
    logs_path = logs_folder / f'{time.strftime("%H-%M-%S")}.rrd'
    
    # Initialize URDF logger
    urdf_logger = URDFLogger(urdf_path)
    
    # Set up coordinate system
    rr.log('origin_axes', rr.Transform3D(translation=[0,0,0], axis_length=0.1), static=True)
    print("Rerun kinematics visualization initialized")
else:
    urdf_logger = None
    if not RERUN_AVAILABLE:
        print("Rerun visualization disabled - missing dependencies")

def kinematics(event):
    global left_wrist_pose, right_wrist_pose, left_finger_poses, right_finger_poses
    
    if event.get('left') != None:
        left_mat_raw = event['left']
        left_mat_numpy = np.array(left_mat_raw, dtype=np.float32).reshape(25,4,4).transpose((0,2,1))
        left_wrist_pose[:] = kbot_vuer_to_urdf_frame @ left_mat_numpy[0]
        left_wrist_pose[:3,3] -= head_matrix[:3,3]
        left_finger_poses[:] = (hand_vuer_to_urdf_frame @ fast_mat_inv(left_mat_numpy[0]) @ left_mat_numpy[1:].T).T

    # Right hand
    if event.get('right') != None:
        right_mat_raw = event['right']
        right_mat_numpy = np.array(right_mat_raw, dtype=np.float32).reshape(25,4,4).transpose((0,2,1))
        right_wrist_pose[:] = kbot_vuer_to_urdf_frame @ right_mat_numpy[0]
        right_wrist_pose[:3,3] -= head_matrix[:3,3]
        right_finger_poses[:] = (hand_vuer_to_urdf_frame @ fast_mat_inv(right_mat_numpy[0]) @ right_mat_numpy[1:].T).T

    hand_target_left = base_to_head_transform @ left_wrist_pose
    hand_target_right = base_to_head_transform @ right_wrist_pose
    
    hand_target_left[2, 3] = max(hand_target_left[2, 3], -0.2)
    hand_target_right[2, 3] = max(hand_target_right[2, 3], -0.2)
    
    # Log target hand positions (what VR hands want)
    if VISUALIZE:
        rr.log('hand_target_left', rr.Transform3D(
            translation=hand_target_left[:3, 3], 
            mat3x3=hand_target_left[:3, :3], 
            axis_length=0.05
        ))
        rr.log('hand_target_right', rr.Transform3D(
            translation=hand_target_right[:3, 3], 
            mat3x3=hand_target_right[:3, :3], 
            axis_length=0.05
        ))
    
    joints = ik_solver.inverse_kinematics(np.array([hand_target_right, hand_target_left]))
    joints = np.asarray(joints)
    
    # Get actual achieved positions from forward kinematics
    actual_positions = ik_solver.forward_kinematics(joints)
    
    # Log actual achieved positions (what robot actually achieves)
    if VISUALIZE:
        rr.log('actual_right', rr.Transform3D(
            translation=actual_positions[0][:3, 3], 
            mat3x3=actual_positions[0][:3, :3], 
            axis_length=0.1
        ))
        rr.log('actual_left', rr.Transform3D(
            translation=actual_positions[1][:3, 3], 
            mat3x3=actual_positions[1][:3, :3], 
            axis_length=0.1
        ))
    
    # Split joints
    left_arm_joints = joints[5:]
    right_arm_joints = joints[:5]
    
    # Log full robot configuration
    if VISUALIZE and urdf_logger:
        new_config = {k: right_arm_joints[i] for i, k in enumerate(ik_solver.active_joints[:5])}
        new_config.update({k: left_arm_joints[i] for i, k in enumerate(ik_solver.active_joints[5:])})
        urdf_logger.log(new_config)
    
    return {
        "joints": {
                "11": float(np.rad2deg(left_arm_joints[0])),
                "12": float(np.rad2deg(left_arm_joints[1])),
                "13": float(np.rad2deg(left_arm_joints[2])),
                "14": float(np.rad2deg(left_arm_joints[3])),
                "15": float(np.rad2deg(left_arm_joints[4])),

                "21": float(np.rad2deg(right_arm_joints[0])),
                "22": float(np.rad2deg(right_arm_joints[1])),
                "23": float(np.rad2deg(right_arm_joints[2])),
                "24": float(np.rad2deg(right_arm_joints[3])),
                "25": float(np.rad2deg(right_arm_joints[4]))
            },
    }
       