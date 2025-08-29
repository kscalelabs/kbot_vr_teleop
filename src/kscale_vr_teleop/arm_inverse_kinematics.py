import time
import numpy as np
from kscale_vr_teleop.util import fast_mat_inv
import ikpy.chain
from pathlib import Path
from scipy.spatial.transform import Rotation
from scipy.optimize import least_squares
from yourdfpy import URDF
from kscale_vr_teleop.analysis.visualizer import ThreadedRobotVisualizer
from scipy.optimize import least_squares
from yourdfpy import URDF

right_arm_links = [
	'base',
	'Torso_Side_Right',
	'KC_C_104R_PitchHardstopDriven',
	'RS03_3',
	'KC_C_202R',
	'KC_C_401R_R_UpForearmDrive',
	'KB_C_501X_Right_Bayonet_Adapter_Hard_Stop'
]

from kscale_vr_teleop._assets import ASSETS_DIR

file_absolute_parent = Path(__file__).parent.absolute()

urdf_path  = str(ASSETS_DIR / "kbot" / "robot.urdf")

def make_robot():
    return URDF.load(
            urdf_path,
            build_scene_graph=True,      # Enable forward kinematics
            build_collision_scene_graph=False,  # Optional: for collision checking
            load_collision_meshes=False,
            load_meshes=True
        )
    
arms_robot = make_robot()

VISUALIZE = False

if VISUALIZE:
    visualizer = ThreadedRobotVisualizer(make_robot)
    visualizer.start_viewer()
    visualizer.add_marker('goal', [0.,0.,0.])

lower_bounds = []
upper_bounds = []
for joint in arms_robot.actuated_joints:
    lower_bounds.append(joint.limit.lower)
    upper_bounds.append(joint.limit.upper)

last_guess = np.zeros(10)
def calculate_arm_joints(head_mat, left_wrist_mat, right_wrist_mat, initial_guess=None):
    global last_guess
    config_base = {
            k.name: 0 for k in arms_robot.actuated_joints
        }
    def residuals(joint_angles):
        config_update = {
            k.name: joint_angles[i] for i, k in enumerate(arms_robot.actuated_joints)
        }
        config_base.update(config_update)
        arms_robot.update_cfg(config_base)
        right_ee_position = arms_robot.get_transform('KB_C_501X_Right_Bayonet_Adapter_Hard_Stop', "base")
        left_ee_position = arms_robot.get_transform('KB_C_501X_Left_Bayonet_Adapter_Hard_Stop', "base")
        right_ee_forward = -right_ee_position[:3,2]
        left_ee_forward = left_ee_position[:3,2]
        right_target_forward = -right_wrist_mat[:3, 2]
        left_target_forward = -left_wrist_mat[:3, 2]
        right_ee_up = -right_ee_position[:3, 1]
        left_ee_up = left_ee_position[:3, 1]
        right_target_up = right_wrist_mat[:3,1]
        left_target_up = left_wrist_mat[:3,1]
        right_rotation_angle_off = np.arccos(np.dot(right_ee_forward, right_target_forward))
        left_rotation_angle_off = np.arccos(np.dot(left_ee_forward, left_target_forward))
        right_y_angle_off = np.arccos(np.dot(right_ee_up, right_target_up))
        left_y_angle_off = np.arccos(np.dot(left_ee_up, left_target_up))
        return np.concatenate([
            right_ee_position[:3, 3] - right_wrist_mat[:3, 3],
            left_ee_position[:3, 3] - left_wrist_mat[:3, 3],
            [0.1*right_rotation_angle_off, 0.1*right_y_angle_off, 0.1*left_rotation_angle_off, 0.1*left_y_angle_off]
        ])
    # 0-2: right position
    # 3-5: left position
    # 6: right direction
    # 7: right rotation
    # 8: left direction
    # 9: left rotation
    jac_sparsity_mat = np.zeros((10, len(arms_robot.actuated_joints)))
    # # joints: evens are right, odds are left, order is shoulder to wrist
    jac_sparsity_mat[:3, :8:2] = 1
    jac_sparsity_mat[6:8, ::2] = 1
    jac_sparsity_mat[3:6, 1:9:2] = 1
    jac_sparsity_mat[8:10, 1::2] = 1

    result = least_squares(
        residuals, 
        last_guess, 
        bounds=(lower_bounds, upper_bounds),
        jac_sparsity=jac_sparsity_mat,
        xtol=1e-3,
        gtol=1e-3,
        ftol=1e-3,
    )
    solution = result.x
    last_guess = solution
    right_joint_angles = solution[::2]
    left_joint_angles = solution[1::2]
    new_config={
        k.name: right_joint_angles[i] for i, k in enumerate(arms_robot.actuated_joints[::2])
    }
    new_config.update({
        k.name: left_joint_angles[i] for i, k in enumerate(arms_robot.actuated_joints[1::2])
    })
    arms_robot.update_cfg(new_config)
    if VISUALIZE:
        visualizer.update_marker('goal', right_wrist_mat[:3, 3], right_wrist_mat[:3, :3])
        visualizer.update_config(new_config)

    return left_joint_angles, right_joint_angles
