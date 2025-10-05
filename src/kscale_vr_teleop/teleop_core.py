import numpy as np
from kscale_vr_teleop.command_conn import Commander16
# from kscale_vr_teleop.udp_conn import UDPHandler
from kscale_vr_teleop.hand_inverse_kinematics import calculate_hand_joints_no_ik
import rerun as rr
from line_profiler import profile
import json
import time
import math

class TeleopCore:
    def __init__(self, websocket, udp_host, udp_port, urdf_logger, ik_solver):
        self.websocket = websocket
        self.head_matrix = np.eye(4, dtype=np.float32)
        self.right_finger_poses = np.zeros((24, 4, 4), dtype=np.float32)
        self.left_finger_poses = np.zeros((24, 4, 4), dtype=np.float32)
        self.right_wrist_pose = np.eye(4,dtype=np.float32)
        self.left_wrist_pose = np.eye(4,dtype=np.float32)

        self.left_wrist_pose[:3,3] = np.array([0.2, 0.2, -0.4])
        self.right_wrist_pose[:3,3] = np.array([0.2, -0.2, -0.4])
        default_wrist_rotation = np.array([
            [0, 0, -1],
            [-1, 0, 0],
            [0, 1, 0]
        ])
        self.left_wrist_pose[:3,:3] = default_wrist_rotation
        self.right_wrist_pose[:3,:3] = default_wrist_rotation

        self.urdf_logger = urdf_logger
        self.ik_solver = ik_solver

        self.base_to_head_transform = np.eye(4)
        self.base_to_head_transform[:3,3] = np.array([0, 0, 0.25])

        self.kinfer_command_handler = Commander16(udp_ip=udp_host, udp_port=udp_port)

        # Gripper values from controller inputs (0.0 to 1.0)
        self.right_gripper_value = 1.0
        self.left_gripper_value = 1.0

        # Joystick values from controller inputs
        self.right_joystick_x = 0.0
        self.right_joystick_y = 0.0
        self.left_joystick_x = 0.0
        self.left_joystick_y = 0.0

        self.use_fingers = False
        self.converged = False
        
        # Track message timing to detect gaps (unpause)
        self.last_message_time = None
        
    def update_head(self, matrix: np.ndarray):
        self.head_matrix = matrix

    def update_joints(self, side: str, fingers: np.ndarray):
        if side == 'left':
            self.left_finger_poses = fingers
        else:
            self.right_finger_poses = fingers
        self.use_fingers = True

    def update_target_location(self, side: str, pose: np.ndarray):
        if side == 'left':
            self.left_wrist_pose = pose
            rr.log('left_wrist', rr.Transform3D(translation=pose[:3, 3], mat3x3=pose[:3, :3], axis_length=0.05))
        else:
            self.right_wrist_pose = pose
            rr.log('right_wrist', rr.Transform3D(translation=pose[:3, 3], mat3x3=pose[:3, :3], axis_length=0.05))

    def update_buttons(self, side: str, gripper_value: float, joystick_x: float, joystick_y: float):
        if side == 'left':
            self.left_gripper_value = gripper_value
            self.left_joystick_x = joystick_x
            self.left_joystick_y = joystick_y
        else:
            self.right_gripper_value = gripper_value
            self.right_joystick_x = joystick_x
            self.right_joystick_y = joystick_y
        self.use_fingers = False

    def _check_message_timing(self):
        """Check time between messages and reset converged flag if gap > 0.5s"""
        current_time = time.time()
        
        if self.last_message_time is not None:
            time_delta = current_time - self.last_message_time
            
            if time_delta >= 0.5:
                print(f"Message gap detected: {time_delta:.3f}s - resetting converged flag")
                self.converged = False
            # else:
            #     print(f"Message received after {time_delta:.3f}s")
        
        self.last_message_time = current_time
    
    def log_joint_angles(self, right_arm: list, left_arm: list):
        new_config = {k: right_arm[i] for i, k in enumerate(self.ik_solver.active_joints[:5])}
        new_config.update({k: left_arm[i] for i, k in enumerate(self.ik_solver.active_joints[5:])})
        self.urdf_logger.log(new_config)
    
    def _compute_gripper_from_fingers(self):
        right_finger_spacing = np.linalg.norm(self.right_finger_poses[8,:3,3] - self.right_finger_poses[3,:3,3])
        right_gripper_joint = 0.068*np.clip(right_finger_spacing/0.15, 0, 1)
        left_finger_spacing = np.linalg.norm(self.left_finger_poses[8,:3,3] - self.left_finger_poses[3,:3,3])
        left_gripper_joint = 0.068*np.clip(left_finger_spacing/0.15, 0, 1)
        return right_gripper_joint, left_gripper_joint
    
    def _compute_gripper_from_controllers(self):
        # Placeholder: map controller trigger/grip values to gripper joint positions
        gripper_range = math.radians(50)
        gripper_start = math.radians(25)
        right_gripper_joint = gripper_start - (gripper_range * (1.0 - self.right_gripper_value))
        left_gripper_joint = gripper_start - (gripper_range * (1.0 - self.left_gripper_value))
        
        # Log gripper positions as scalars for timeseries visualization
        rr.log("plots/gripper_positions/Right Gripper", rr.Scalars(right_gripper_joint))
        rr.log("plots/gripper_positions/Left Gripper", rr.Scalars(left_gripper_joint))

        return right_gripper_joint, left_gripper_joint

    @profile
    async def compute_joint_angles(self):
        '''
        Returns (right_arm_joints, left_arm_joints, right_finger_angles, left_finger_angles)
        where right_arm_joints and left_arm_joints are lists of 6 floats (5 arm joints + gripper),
        and right_finger_angles, left_finger_angles are np.ndarray of 6 floats (thumb_metacarpal + thumb + 4 fingers).
        '''
        hand_target_left = self.base_to_head_transform @ self.left_wrist_pose
        hand_target_right = self.base_to_head_transform @ self.right_wrist_pose

        hand_target_left[2, 3] = max(hand_target_left[2, 3], -0.25)
        hand_target_right[2, 3] = max(hand_target_right[2, 3], -0.25)
        rr.log('target_right', rr.Transform3D(translation=hand_target_right[:3, 3], mat3x3=hand_target_right[:3, :3], axis_length=0.1))
        rr.log('target_left', rr.Transform3D(translation=hand_target_left[:3, 3], mat3x3=hand_target_left[:3, :3], axis_length=0.1))
        # clamp hand targets z coordinate to be above -0.2
        joints = self.ik_solver.inverse_kinematics(np.array([hand_target_right, hand_target_left]))
        # Convert JAX array to NumPy for faster slicing operations
        joints = np.asarray(joints)
        left_arm_joints = joints[5:]
        right_arm_joints = joints[:5]

        if self.use_fingers:
            right_gripper_joint, left_gripper_joint = self._compute_gripper_from_fingers()
        else:
            right_gripper_joint, left_gripper_joint = self._compute_gripper_from_controllers()

        # Compute finger joint angles (6 per hand: thumb_metacarpal + thumb + 4 fingers)
        if self.use_fingers:
            left_finger_angles, right_finger_angles = calculate_hand_joints_no_ik(self.left_finger_poses, self.right_finger_poses)
        else:
            left_finger_angles = np.zeros(6, dtype=np.float32)
            right_finger_angles = np.zeros(6, dtype=np.float32)
            left_finger_angles[-1] = 1
            right_finger_angles[-1] = 1
            left_finger_angles[:-1] = self.left_gripper_value
            right_finger_angles[:-1] = self.right_gripper_value
        # Ensure finger angles are clipped to 0-1 (no trimming; keep all 6)
        right_finger_angles = np.clip(right_finger_angles, 0, 1)
        left_finger_angles = np.clip(left_finger_angles, 0, 1)

        # Log finger angles for timeseries visualization
        for i, finger in enumerate(['thumb', 'index', 'middle', 'ring', 'pinky', 'thumb_yaw']):
            rr.log(f"plots/finger_angles/right/{finger}", rr.Scalars(right_finger_angles[i]))
            rr.log(f"plots/finger_angles/left/{finger}", rr.Scalars(left_finger_angles[i]))

        # Compute actual end effector poses using forward kinematics
        # Combine right and left arm joints (5 each) into the expected 10-element array
        all_joint_angles = np.concatenate([right_arm_joints, left_arm_joints])
        actual_poses = self.ik_solver.forward_kinematics(all_joint_angles)
        
        # Extract actual poses for right and left arms
        actual_right_pose = actual_poses[0]  # First end effector (right arm)
        actual_left_pose = actual_poses[1]   # Second end effector (left arm)
        
        # Log actual end effector poses for visualization
        rr.log('actual_right', rr.Transform3D(
            translation=actual_right_pose[:3, 3], 
            mat3x3=actual_right_pose[:3, :3], 
            axis_length=0.1
        ))
        rr.log('actual_left', rr.Transform3D(
            translation=actual_left_pose[:3, 3], 
            mat3x3=actual_left_pose[:3, :3], 
            axis_length=0.05
        ))
        
        # Calculate distances between target and actual positions
        # Target positions: hand_target_left/right (what VR hands want)
        # Actual positions: actual_left/right_pose (where robot actually is)
        right_distance = np.linalg.norm(hand_target_right[:3, 3] - actual_right_pose[:3, 3])
        left_distance = np.linalg.norm(hand_target_left[:3, 3] - actual_left_pose[:3, 3])
        
        # Log distances for visualization
        rr.log("plots/tracking_accuracy/Right Distance", rr.Scalars(right_distance))
        rr.log("plots/tracking_accuracy/Left Distance", rr.Scalars(left_distance))
        
        payload = {
            "type": "kinematics",
            "joysticks": {
                "right":{
                    "x": self.right_joystick_x, 
                    "y": self.right_joystick_y
                },
                "left": {
                    "x": self.left_joystick_x,
                    "y": self.left_joystick_y
                }
            },
            "joints": {
                "right": right_arm_joints.tolist(), 
                "left": left_arm_joints.tolist()
            },
            "distances": {
                "right": float(right_distance),
                "left": float(left_distance)
            }
        }
        self._check_message_timing()
        if (right_distance < 0.025 and left_distance < 0.025):
            self.converged = True
        if self.converged:
            self.log_joint_angles(right_arm_joints, left_arm_joints)
            self.kinfer_command_handler.update_commands (
                right_arm_joints.tolist() + [right_gripper_joint],
                left_arm_joints.tolist() + [left_gripper_joint],
                (self.right_joystick_x, self.right_joystick_y),
                (self.left_joystick_x, self.left_joystick_y)
                )
            await self.websocket.send(json.dumps(payload))
 

    async def compute_and_send_joints(self):
        await self.compute_joint_angles()
        self.kinfer_command_handler.send_commands()


        

    # def send_kos_commands(self, right_arm: list, left_arm: list):
    #     '''
    #     Takes input in the same format as compute_joint_angles arm output
    #     '''
    #     self.kos_command_handler._send_udp(right_arm, left_arm)