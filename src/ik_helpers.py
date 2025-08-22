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

        result = least_squares(residuals, self.last_guess, bounds=(self.lower_bounds, self.upper_bounds))
        self.last_guess = result.x
        return self.last_guess
