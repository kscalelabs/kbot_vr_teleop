import numpy as np
from scipy.spatial.transform import Rotation

from util import fast_mat_inv

def calculate_hand_joints(left_hand_mat, right_hand_mat):
    '''
    Both mats are 25x4x4 in urdf frame.
    '''
    tip_indices = [4, 9, 14, 19, 24]
    metacarpal_indices = [1, 5, 10, 15, 20]
    thumb_metacarpal_index=1 # used for yaw control
    thumb_pitch_index = 2
    tip_poses_relative_to_metacarpals = np.array([
        fast_mat_inv(right_hand_mat[metacarpal_indices[i]]) @ right_hand_mat[tip_indices[i]]
        for i in range(5)
    ])
    tip_y_angles = np.arctan2(tip_poses_relative_to_metacarpals[:, 2, 0], tip_poses_relative_to_metacarpals[:, 2, 2])

    right_joints = np.zeros(6)
    right_joints[:5] = tip_y_angles

    thumb_tip_rel_to_wrist = fast_mat_inv(right_hand_mat[0]) @ right_hand_mat[4]
    # print(thumb_tip_rel_to_wrist[1, 3]) # 0 to -0.1, scale to 0 to 2pi
    thumb_yaw_angle = -thumb_tip_rel_to_wrist[1, 3] / 0.1 * 2*np.pi

    right_joints_scaled = right_joints + 2*np.pi*(right_joints<0)
    right_joints_scaled[5] = thumb_yaw_angle


    # jank scaling:
    # subtract pi from thumb pitch
    right_joints_scaled[0] -= np.pi
    # rescale angles to take up full range
    right_joints_scaled[:5]*=2

    return np.zeros(6), right_joints_scaled