import numpy as np
from util import fast_mat_inv
import ikpy.chain
from pathlib import Path
from scipy.spatial.transform import Rotation
from scipy.optimize import least_squares

file_absolute_parent = Path(__file__).parent.absolute()

right_chain = ikpy.chain.Chain.from_urdf_file(
    f"{file_absolute_parent}/assets/kbot/robot.urdf",
    base_elements=['dof_right_shoulder_pitch_03'],  # Start from the torso and let ikpy auto-discover
    base_element_type='joint'
)

def from_scratch_ik(target_position, kinematic_chain: ikpy.chain.Chain, initial_guess):
    def residuals(joint_angles):
        frame_mat = kinematic_chain.forward_kinematics(joint_angles)
        return (frame_mat[:3, 3] - target_position).tolist()

    result = least_squares(residuals, initial_guess)
    return result.x

# left_chain = ikpy.chain.Chain.from_urdf_file(
#     f"{file_absolute_parent}/assets/kbot/robot.urdf",
#     base_elements=['Torso_Side_Left']  # Start from the torso and let ikpy auto-discover
#     base_element_type='joint'
# )

class ArmIKSolver:
    def __init__(self, kinematic_chain: ikpy.chain.Chain):
        self.kinematic_chain = kinematic_chain
        self.last_guess = np.zeros(6)

    def from_scratch_ik(self, target_position): # This shouldn't be necessary but ikpy's inverse kinematics is ironically crap
        def residuals(joint_angles):
            frame_mat = self.kinematic_chain.forward_kinematics(joint_angles)
            return frame_mat[:3, 3] - target_position

        result = least_squares(residuals, self.last_guess)
        self.last_guess = result.x
        return self.last_guess

solver = ArmIKSolver(right_chain)

def calculate_arm_joints(head_mat, left_wrist_mat, right_wrist_mat):
    left_wrist_relative_to_head = left_wrist_mat @ fast_mat_inv(head_mat)
    right_wrist_relative_to_head = right_wrist_mat @ fast_mat_inv(head_mat)
    right_wrist_mat[:3, 3] += np.array([0,0,-1.5]) # move down to roughly match urdf coordinate system
    # print(right_wrist_mat[:3,3])

    right_joint_angles = solver.from_scratch_ik(target_position=right_wrist_mat[:3,3])
    # print(right_joint_angles.tolist())

    # right_joint_angles = np.zeros(6)

    print(right_joint_angles)
    actual_hand_pose = right_chain.forward_kinematics(right_joint_angles)
    # print(actual_hand_pose[:3,3])

    # print("-"*10)
    # print(Rotation.from_matrix(head_mat[:3,:3]).apply(np.eye(3)[0]))
    # print(right_wrist_relative_to_head[:3,3])


    return np.zeros(5), right_joint_angles[:5]