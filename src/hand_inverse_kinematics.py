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

def calculate_hand_joints(left_fingers_mat, right_fingers_mat):
    '''
    Both mats are 25x4x4 in urdf frame.
    '''
    # indices are 1 less than what the docs say because we exclude the wrist pose (all of these are relative to the wrist)
    tip_indices = [3, 8, 13, 18, 23]
    metacarpal_indices = [1, 5, 10, 15, 20]
    tip_poses_relative_to_metacarpals = np.array([
        fast_mat_inv(right_fingers_mat[metacarpal_indices[i]]) @ right_fingers_mat[tip_indices[i]]
        for i in range(5)
    ])
    tip_y_angles = np.arctan2(tip_poses_relative_to_metacarpals[:, 2, 0], tip_poses_relative_to_metacarpals[:, 2, 2])

    right_joints = np.zeros(6)
    right_joints[:5] = tip_y_angles
    right_joints_scaled = right_joints + 2*np.pi*(right_joints<0)

    # print(right_fingers_mat[8,:3,0], right_fingers_mat[8,:3, 3])
    # def residuals(joint_angles):
    #     hand_robot.update_cfg({
    #         "R_thumb_proximal_pitch_joint": joint_angles[0],
    #         "R_thumb_proximal_yaw_joint": joint_angles[1],
    #     })
    #     frame_transform = hand_robot.get_transform("R_thumb_tip", "R_hand_base_link")
    #     return frame_transform[:3, 3] - thumb_tip_rel_to_wrist[:3, 3]

    # optimized_joint_angles = scipy.optimize.least_squares(residuals, right_joints[:2])
    # right_joints_scaled[0] = optimized_joint_angles.x[0]
    # right_joints_scaled[5] = optimized_joint_angles.x[1]
    # print(residuals(optimized_joint_angles.x))


    # jank scaling:
    # subtract pi from thumb pitch
    # right_joints_scaled[0] += np.pi/2
    # rescale angles to take up full range
    right_joints_scaled[1:5]*=2
    # print(right_joints_scaled)

    return np.zeros(6), right_joints_scaled
