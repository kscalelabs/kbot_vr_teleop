import numpy as np
import scipy
from scipy.spatial.transform import Rotation

from util import fast_mat_inv
import ikpy.chain
from yourdfpy import URDF
from pathlib import Path

file_absolute_parent = Path(__file__).parent.absolute()

hand_robot  = URDF.load(
        f"{file_absolute_parent}/assets/inspire_hand/inspire_hand_right.urdf",
        build_scene_graph=True,      # Enable forward kinematics
        build_collision_scene_graph=False,  # Optional: for collision checking
        load_collision_meshes=False
    )

last_optim_res =  np.array([*np.zeros(6), 1])

def calculate_hand_joints(left_fingers_mat, right_fingers_mat):
    global last_optim_res
    '''
    Both mats are 25x4x4 in urdf frame.
    '''
    # indices are 1 less than what the docs say because we exclude the wrist pose (all of these are relative to the wrist)
    tip_indices = [3, 8, 13, 18, 23]

    lower_bounds = []
    upper_bounds = []
    for joint in hand_robot.actuated_joints:
        lower_bounds.append(joint.limit.lower)
        upper_bounds.append(joint.limit.upper)
    # print(right_fingers_mat[8,:3,0], right_fingers_mat[8,:3, 3])
    def residuals(joint_angles_and_scale):
        hand_robot.update_cfg({
            "R_thumb_proximal_pitch_joint": joint_angles_and_scale[0],
            "R_thumb_proximal_yaw_joint": joint_angles_and_scale[1],
            "R_index_proximal_joint": joint_angles_and_scale[2],
            "R_middle_proximal_joint": joint_angles_and_scale[3],
            "R_ring_proximal_joint": joint_angles_and_scale[4],
            "R_pinky_proximal_joint": joint_angles_and_scale[5],
        })
        thumb_position = hand_robot.get_transform("R_thumb_tip", "R_hand_base_link")
        index_position = hand_robot.get_transform("R_index_tip", "R_hand_base_link")
        middle_position = hand_robot.get_transform("R_middle_tip", "R_hand_base_link")
        ring_position = hand_robot.get_transform("R_ring_tip", "R_hand_base_link")
        pinky_position = hand_robot.get_transform("R_pinky_tip", "R_hand_base_link")
        scale_factor = joint_angles_and_scale[6]
        return (np.array([
            thumb_position[:3, 3],
            index_position[:3, 3],
            middle_position[:3, 3],
            ring_position[:3, 3],
            pinky_position[:3, 3],
        ]) - scale_factor * right_fingers_mat[tip_indices, :3, 3]).flatten()
    

    optim_res = scipy.optimize.least_squares(residuals, last_optim_res, bounds=(tuple(lower_bounds)+(0.1,), tuple(upper_bounds)+(2,)))
    last_optim_res = optim_res.x
    # print(np.linalg.norm(residuals(optim_res.x)))
    scaled_to_bounds = np.array([
        (x-lb) / (ub-lb) for x, lb, ub in zip(optim_res.x, lower_bounds, upper_bounds)
    ])
    reordered_correctly = scaled_to_bounds[[0,2,3,4,5,1]]

    return np.zeros(6), reordered_correctly
