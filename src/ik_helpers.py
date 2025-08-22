import numpy as np
import ikpy.chain
from scipy.optimize import least_squares
class IKSolver:
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

