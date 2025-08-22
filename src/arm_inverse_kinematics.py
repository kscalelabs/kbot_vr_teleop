import numpy as np
from util import fast_mat_inv

def calculate_arm_joints(head_mat, left_wrist_mat, right_wrist_mat):
    left_wrist_relative_to_head = left_wrist_mat @ fast_mat_inv(head_mat)
    right_wrist_relative_to_head = right_wrist_mat @ fast_mat_inv(head_mat)
    return np.zeros(5), np.zeros(5)