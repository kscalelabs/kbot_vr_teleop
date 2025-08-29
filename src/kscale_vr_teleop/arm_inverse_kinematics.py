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

class IKSolver:
    def __init__(self, robot: URDF):
        self.robot = robot
        self.last_guess = np.zeros(len(robot.actuated_joints)//2)
        self.lower_bounds = []
        self.upper_bounds = []
        for joint in self.robot.actuated_joints[::2]:
            self.lower_bounds.append(joint.limit.lower)
            self.upper_bounds.append(joint.limit.upper)

    def from_scratch_ik(self, target_mat, frame_name, initial_guess = None): # This shouldn't be necessary but ikpy's inverse kinematics is ironically crap
        config_base = {
                k.name: 0 for k in self.robot.actuated_joints
            }
        def residuals(joint_angles):
            config_update = {
                k.name: joint_angles[i] for i, k in enumerate(self.robot.actuated_joints[::2] if 'Right' in frame_name else self.robot.actuated_joints[1::2])
            }
            config_base.update(config_update)
            self.robot.update_cfg(config_base)
            ee_position = self.robot.get_transform(frame_name, "base")
            ee_forward = -ee_position[:3, 2] if 'Right' in frame_name else ee_position[:3, 2]
            target_forward = -target_mat[:3, 2]
            ee_up = -ee_position[:3, 1] if 'Right' in frame_name else ee_position[:3,1]
            target_up = target_mat[:3,1] 
            rotation_angle_off = np.arccos(np.dot(ee_forward, target_forward))
            y_angle_off = np.arccos(np.dot(ee_up, target_up))
            return np.concatenate([
                ee_position[:3, 3] - target_mat[:3, 3],
                [0.1*rotation_angle_off, 0.1*y_angle_off]
            ])
        jac_sparsity_mat = np.zeros((5, len(self.robot.actuated_joints)//2))
        jac_sparsity_mat[0:4,0] = 1
        jac_sparsity_mat[0:4,1] = 1
        jac_sparsity_mat[0:4,2] = 1
        jac_sparsity_mat[0:4,3] = 1
        jac_sparsity_mat[4,4] = 0

        SOLVE_WITH_BOUNDS = True
        result = least_squares(
            residuals, 
            self.last_guess, 
            bounds=(self.lower_bounds, self.upper_bounds) if SOLVE_WITH_BOUNDS else (-np.inf, np.inf), 
            jac_sparsity=jac_sparsity_mat,
            xtol=1e-3,
            gtol=1e-5,
            ftol=1e-2,
        )
        solution = result.x
        self.last_guess = solution
        return solution


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

right_solver = IKSolver(arms_robot)
left_solver = IKSolver(arms_robot)

def calculate_arm_joints(head_mat, left_wrist_mat, right_wrist_mat, initial_guess=None):
    right_joint_angles = right_solver.from_scratch_ik(target_mat=right_wrist_mat, frame_name = 'KB_C_501X_Right_Bayonet_Adapter_Hard_Stop', initial_guess = initial_guess)
    left_joint_angles = left_solver.from_scratch_ik(target_mat=left_wrist_mat, frame_name = 'KB_C_501X_Left_Bayonet_Adapter_Hard_Stop', initial_guess = initial_guess)
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
