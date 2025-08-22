import numpy as np

def calculate_hand_joints(left_hand_mat, right_hand_mat):
    '''
    Both mats are 25x4x4 in urdf frame.
    '''

    left_poses_relative_to_wrist = left_hand_mat[1:] @ left_hand_mat[0]
    right_poses_relative_to_wrist = right_hand_mat[1:] @ right_hand_mat[0]

    return np.zeros(5), np.zeros(5)