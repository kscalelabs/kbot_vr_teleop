import numpy as np
from scipy.optimize import least_squares
from yourdfpy import URDF

class IKSolver:
    def __init__(self, robot: URDF):
        self.robot = robot
        self.last_guess = np.zeros(len(robot.actuated_joints))
        self.lower_bounds = []
        self.upper_bounds = []
        for joint in self.robot.actuated_joints:
            self.lower_bounds.append(joint.limit.lower)
            self.upper_bounds.append(joint.limit.upper)

    def from_scratch_ik(self, target_position, frame_name): # This shouldn't be necessary but ikpy's inverse kinematics is ironically crap
        def residuals(joint_angles):
            self.robot.update_cfg({
                k.name: joint_angles[i] for i, k in enumerate(self.robot.actuated_joints)
            })
            ee_position = self.robot.get_transform(frame_name, "base")
            return ee_position[:3, 3] - target_position
        
        jac_sparsity_mat = np.zeros((1, len(self.robot.actuated_joints)))
        jac_sparsity_mat[0,0] = 1
        jac_sparsity_mat[0,2] = 1
        jac_sparsity_mat[0,4] = 1
        jac_sparsity_mat[0,6] = 1

        SOLVE_WITH_BOUNDS = True
        result = least_squares(residuals, self.last_guess, bounds=(self.lower_bounds, self.upper_bounds) if SOLVE_WITH_BOUNDS else (-np.inf, np.inf), jac_sparsity=np.repeat(jac_sparsity_mat, 3, axis=0))
        solution = result.x
        self.last_guess = solution
        # if not SOLVE_WITH_BOUNDS:
        #     solution = np.clip(solution, self.lower_bounds, self.upper_bounds)
        return solution
