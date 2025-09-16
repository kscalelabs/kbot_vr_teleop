import numpy as np
from scipy.spatial.transform import Rotation

from kscale_vr_teleop.util import fast_mat_inv
from pathlib import Path
import warnings

file_absolute_parent = Path(__file__).parent.absolute()

last_optim_res =  np.array([*np.zeros(6), 1])

def calculate_hand_joints_no_ik(left_fingers_mat, right_fingers_mat):
    """
    Compute 6 finger joint angles per hand from 24x4x4 finger poses (relative to wrist).
    Returns: left_finger_angles (np.array[6]), right_finger_angles (np.array[6])
    Joint order: [thumb_metacarpal, thumb_curl, index_curl, middle_curl, ring_curl, pinky_curl]
    Angles normalized to 0-1 (0=open, 1=closed).
    """
    tip_indices = [3, 8, 13, 18, 23]  # Thumb tip, index, middle, ring, pinky tips
    metacarpal_indices = [0, 4, 9, 14, 20]  # Corresponding metacarpal bases

    # Right hand computation
    right_tips_relative_to_metacarpals = np.array([
        fast_mat_inv(right_fingers_mat[i]) @ right_fingers_mat[j] 
        for i, j in zip(metacarpal_indices, tip_indices)
    ])
    try:
        right_angles = Rotation.from_matrix(right_tips_relative_to_metacarpals[:,:3,:3]).as_euler('XYZ', degrees=False)[:,0]
        # Normalize: 
        right_angles = (right_angles - 1.5) % (2 * np.pi)  
        thumb_angle = (right_angles[0] - 3.0) / (5.3 - 3.0)  # Thumb-specific normalization
        other_angles = (right_angles[1:] - 0.4) / (4.8 - 0.4)  
        right_finger_angles = np.array([thumb_angle] + other_angles.tolist())
        # Add thumb metacarpal angle (from wrist-relative thumb base rotation)
        thumb_metacarpal_angle = Rotation.from_matrix(right_fingers_mat[0,:3,:3]).as_euler('XYZ', degrees=False)[1]
        right_finger_angles = np.insert(right_finger_angles, 0, thumb_metacarpal_angle)  
        right_finger_angles = np.clip(1 - right_finger_angles, 0, 1)  # Invert
    except ValueError as e:
        warnings.warn(f"ValueError in right hand computation: {e}")
        right_finger_angles = np.zeros(6)

    # Left hand computation 
    left_tips_relative_to_metacarpals = np.array([
        fast_mat_inv(left_fingers_mat[i]) @ left_fingers_mat[j] 
        for i, j in zip(metacarpal_indices, tip_indices)
    ])
    try:
        left_angles = Rotation.from_matrix(left_tips_relative_to_metacarpals[:,:3,:3]).as_euler('XYZ', degrees=False)[:,0]
        # Normalize:
        left_angles = (left_angles - 1.5) % (2 * np.pi)  # Unwrap
        thumb_angle = (left_angles[0] - 3.0) / (5.3 - 3.0)
        other_angles = (left_angles[1:] - 0.4) / (4.8 - 0.4)
        left_finger_angles = np.array([thumb_angle] + other_angles.tolist())
        # Add thumb metacarpal (from left thumb base rotation)
        thumb_metacarpal_angle = Rotation.from_matrix(left_fingers_mat[0,:3,:3]).as_euler('XYZ', degrees=False)[1]
        left_finger_angles = np.insert(left_finger_angles, 0, thumb_metacarpal_angle)  # Prepend metacarpal
        left_finger_angles = np.clip(1 - left_finger_angles, 0, 1)  # Invert
    except ValueError as e:
        warnings.warn(f"ValueError in left hand computation: {e}")
        left_finger_angles = np.zeros(6)

    return left_finger_angles, right_finger_angles