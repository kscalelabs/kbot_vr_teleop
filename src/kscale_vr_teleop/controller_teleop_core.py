import numpy as np
from kscale_vr_teleop._assets import ASSETS_DIR
from kscale_vr_teleop.analysis.rerun_loader_urdf import URDFLogger
from kscale_vr_teleop.jax_ik import RobotInverseKinematics
from kscale_vr_teleop.command_conn import Commander16
from kscale_vr_teleop.udp_conn import UDPHandler
import rerun as rr
from line_profiler import profile

class ControllerTeleopCore:
    def __init__(self, udp_host='localhost', udp_port=10000):
        self.head_matrix = np.eye(4, dtype=np.float32)
        
        # Controller poses instead of finger poses
        self.right_controller_pose = np.eye(4, dtype=np.float32)
        self.left_controller_pose = np.eye(4, dtype=np.float32)
        
        # Gripper values from controller inputs (0.0 to 1.0)
        self.right_gripper_value = 0.0
        self.left_gripper_value = 0.0

        # Default controller positions
        self.left_controller_pose[:3,3] = np.array([0.2, 0.2, -0.4])
        self.right_controller_pose[:3,3] = np.array([0.2, -0.2, -0.4])
        default_controller_rotation = np.array([
            [0, 0, -1],
            [-1, 0, 0],
            [0, 1, 0]
        ])
        self.left_controller_pose[:3,:3] = default_controller_rotation
        self.right_controller_pose[:3,:3] = default_controller_rotation

        self.urdf_path = str(ASSETS_DIR / "kbot_legless" / "robot.urdf")
        self.urdf_logger = URDFLogger(self.urdf_path)
        self.ik_solver = RobotInverseKinematics(self.urdf_path, ['PRT0001', 'PRT0001_2'], 'base')

        self.base_to_head_transform = np.eye(4)
        self.base_to_head_transform[:3,3] = np.array([0, 0, 0.25])

        self.kinfer_command_handler = Commander16(udp_ip=udp_host, udp_port=udp_port)
        self.kos_command_handler = UDPHandler(udp_host=udp_host, udp_port=udp_port)
        self.log_joint_angles(np.zeros(5), np.zeros(5))

    def update_head(self, matrix: np.ndarray):
        self.head_matrix = matrix

    def update_left_controller(self, pose: np.ndarray, gripper_value: float):
        """Update left controller pose and gripper value"""
        self.left_controller_pose = pose
        self.left_gripper_value = gripper_value
        rr.log('left_controller', rr.Transform3D(
            translation=self.left_controller_pose[:3, 3], 
            mat3x3=self.left_controller_pose[:3, :3], 
            axis_length=0.05
        ))
    
    def update_right_controller(self, pose: np.ndarray, gripper_value: float):
        """Update right controller pose and gripper value"""
        self.right_controller_pose = pose
        self.right_gripper_value = gripper_value
        rr.log('right_controller', rr.Transform3D(
            translation=self.right_controller_pose[:3, 3], 
            mat3x3=self.right_controller_pose[:3, :3], 
            axis_length=0.05
        ))

    def log_joint_angles(self, right_arm: list, left_arm: list):
        new_config = {k: right_arm[i] for i, k in enumerate(self.ik_solver.active_joints[:5])}
        new_config.update({k: left_arm[i] for i, k in enumerate(self.ik_solver.active_joints[5:])})
        self.urdf_logger.log(new_config)

    @profile
    def compute_joint_angles(self):
        '''
        Returns (right_arm_joints, left_arm_joints)
        '''
        hand_target_left = self.base_to_head_transform @ self.left_controller_pose
        hand_target_right = self.base_to_head_transform @ self.right_controller_pose

        rr.log('target_right', rr.Transform3D(
            translation=hand_target_right[:3, 3], 
            mat3x3=hand_target_right[:3, :3], 
            axis_length=0.1
        ))
        rr.log('target_left', rr.Transform3D(
            translation=hand_target_left[:3, 3], 
            mat3x3=hand_target_left[:3, :3], 
            axis_length=0.1
        ))
        
        # clamp hand targets z coordinate to be above -0.2
        hand_target_left[2, 3] = max(hand_target_left[2, 3], -0.2)
        hand_target_right[2, 3] = max(hand_target_right[2, 3], -0.2)
        
        joints = self.ik_solver.inverse_kinematics(np.array([hand_target_right, hand_target_left]))
        # Convert JAX array to NumPy for faster slicing operations
        joints = np.asarray(joints)
        
        left_arm_joints = joints[5:]
        right_arm_joints = joints[:5]
        
        # Convert controller trigger/grip values to gripper joint positions
        # 0.068 appears to be the maximum gripper opening
        right_gripper_joint = 0.068 * (1.0 - self.right_gripper_value)  # Inverted: 1.0 = closed, 0.0 = open
        left_gripper_joint = 0.068 * (1.0 - self.left_gripper_value)

        # Log gripper positions as scalars for timeseries visualization
        rr.log("plots/gripper_positions/Right Gripper", rr.Scalar(right_gripper_joint))
        rr.log("plots/gripper_positions/Left Gripper", rr.Scalar(left_gripper_joint))

        return right_arm_joints.tolist() + [right_gripper_joint], left_arm_joints.tolist() + [left_gripper_joint]
    
    def send_kinfer_commands(self, right_arm: list, left_arm: list):
        '''
        Takes input in the same format as compute_joint_angles output
        '''
        self.kinfer_command_handler.send_commands(right_arm, left_arm)

    def send_kos_commands(self, right_arm: list, left_arm: list):
        '''
        Takes input in the same format as compute_joint_angles output
        '''
        self.kos_command_handler._send_udp(right_arm, left_arm)
