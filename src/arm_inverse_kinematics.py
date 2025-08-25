import numpy as np
from util import fast_mat_inv
import ikpy.chain
from ik_helpers import IKSolver
from pathlib import Path
from scipy.spatial.transform import Rotation
from scipy.optimize import least_squares
from yourdfpy import URDF
from visualizer import ThreadedRobotVisualizer

file_absolute_parent = Path(__file__).parent.absolute()

right_chain = ikpy.chain.Chain.from_urdf_file(
    f"{file_absolute_parent}/assets/kbot/robot.urdf",
    base_elements=['base'],  # Start from the torso and let ikpy auto-discover
    # base_element_type='joint'
)

def make_robot():
    return URDF.load(
            f"{file_absolute_parent}/assets/kbot/robot.urdf",
            build_scene_graph=True,      # Enable forward kinematics
            build_collision_scene_graph=False,  # Optional: for collision checking
            load_collision_meshes=False,
            load_meshes=True
        )
    
arms_robot = make_robot()

VISUALIZE = True

if VISUALIZE:
    visualizer = ThreadedRobotVisualizer(make_robot)
    visualizer.start_viewer()
    visualizer.add_marker('goal', [0.,0.,0.])


# left_chain = ikpy.chain.Chain.from_urdf_file(
#     f"{file_absolute_parent}/assets/kbot/robot.urdf",
#     base_elements=['Torso_Side_Left']  # Start from the torso and let ikpy auto-discover
#     base_element_type='joint'
# )

solver = IKSolver(arms_robot)

def calculate_arm_joints(head_mat, left_wrist_mat, right_wrist_mat):
    # right_wrist_mat = right_wrist_mat.copy()
    # right_wrist_mat[:3, 3] += np.array([0,0,-1.5]) # move down to roughly match urdf coordinate system

    right_joint_angles = solver.from_scratch_ik(target_position=right_wrist_mat[:3,3], frame_name = 'KB_C_501X_Right_Bayonet_Adapter_Hard_Stop')
    # right_joint_angles = solver.from_scratch_ik(target_position=right_wrist_mat[:3,3])
    new_config={
        k.name: right_joint_angles[i] for i, k in enumerate(arms_robot.actuated_joints)
    }
    arms_robot.update_cfg(new_config)
    if VISUALIZE:
        visualizer.update_marker('goal', right_wrist_mat[:3, 3], right_wrist_mat[:3, :3])
        visualizer.update_config(new_config)
    print(right_wrist_mat[:3, 3], arms_robot.get_transform('KB_C_501X_Right_Bayonet_Adapter_Hard_Stop', 'base')[:3,3])

    return np.zeros(5), right_joint_angles[::2]

def new_calculate_arm_joints(head_mat, left_wrist_mat, right_wrist_mat):
    # right_wrist_mat[:3, 3] += np.array([0,0,-1.5]) # move down to roughly match urdf coordinate system
    ik_solution = right_chain.inverse_kinematics(target_position = right_wrist_mat[:3, 3])

    new_config={
        k.name: ik_solution[1:-1][i//2] for i, k in enumerate(arms_robot.actuated_joints)
    }
    arms_robot.update_cfg(new_config)
    # if VISUALIZE:
    #     visualizer.update_marker('goal', right_wrist_mat[:3, 3], right_wrist_mat[:3, :3])
    #     visualizer.update_config(new_config)

    return np.zeros(5), ik_solution[1:-1]  # ikpy includes dummy links on both ends of the kinematic chain