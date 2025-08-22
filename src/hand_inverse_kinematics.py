import numpy as np

def fast_mat_inv(mat):
    ret = np.eye(4)
    ret[:3, :3] = mat[:3, :3].T
    ret[:3, 3] = -mat[:3, :3].T @ mat[:3, 3]
    return ret

def calculate_hand_joints(left_hand_mat, right_hand_mat):
    '''
    Both mats are 25x4x4 in urdf frame.
    '''
    tip_indices = [4, 9, 14, 19, 24]
    knuckle_indices = [2,7,12,17,22]
    thumb_metacarpal_index=1 # used for yaw control
    left_poses_relative_to_wrist = left_hand_mat @ fast_mat_inv(left_hand_mat[0])
    right_poses_relative_to_wrist = right_hand_mat @ fast_mat_inv(right_hand_mat[0])


    return np.zeros(6), np.zeros(6)