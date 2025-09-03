import numpy as np
from scipy.spatial.transform import Rotation

from kscale_vr_teleop.util import fast_mat_inv
from pathlib import Path

from kscale_vr_teleop._assets import ASSETS_DIR

file_absolute_parent = Path(__file__).parent.absolute()

last_optim_res =  np.array([*np.zeros(6), 1])

def calculate_hand_joints_no_ik(left_fingers_mat, right_fingers_mat):
    left_joints = np.zeros(6)

    tip_indices = [3, 8, 13, 18, 23]
    metacarpal_indices = [0,4,9,14,20]

    tips_relative_to_metacarpals = np.array([
        fast_mat_inv(right_fingers_mat[i]) @ right_fingers_mat[j] for i, j in zip(metacarpal_indices, tip_indices)
    ])
    try:
        angles = Rotation.from_matrix(tips_relative_to_metacarpals[:,:3,:3]).as_euler('XYZ', degrees=False)[:,0]
        angles = (angles-1.5) % (2*np.pi)
        angles[1:] = (angles[1:] - 0.4) / (4.8 - 0.4)
        angles[0] = (angles[0] - 3.0) / (5.3 - 3.0)
        angles_list = angles.tolist()
        thumb_metacarpal_angles = Rotation.from_matrix(right_fingers_mat[0,:3,:3]).as_euler('XYZ', degrees=False).tolist()[1]

        combined_angles = np.clip(angles_list+[thumb_metacarpal_angles], 0, 1)
        combined_angles[:-1] = 1-combined_angles[:-1]

        return left_joints, combined_angles
    except ValueError:
        print("ValueError in hand position no ik function")
        return np.zeros(6), np.zeros(6)
