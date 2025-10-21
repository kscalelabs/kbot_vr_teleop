import numpy as np
import json
import time
import math

from line_profiler import profile

from kscale_vr_teleop.command_conn import Commander16
from kscale_vr_teleop.hand_inverse_kinematics import calculate_hand_joints_no_ik

class TeleopCore:
    def __init__(self, websocket, udp_host, udp_port, ik_solver):
        self.kinfer_command_handler = Commander16(udp_ip=udp_host, udp_port=udp_port)
        self.websocket = websocket
        self.ik_solver = ik_solver

        self.base_to_head_transform = np.eye(4)
        self.base_to_head_transform[:3,3] = np.array([0, 0, 0.25])
        self.right_wrist_pose = np.eye(4,dtype=np.float32)
        self.left_wrist_pose = np.eye(4,dtype=np.float32)
        # Gripper values from controller inputs (0.0 to 1.0)
        self.right_gripper_value = 1.0
        self.left_gripper_value = 1.0
        self.left_wrist_pose[:3,3] = np.array([0.2, 0.2, -0.4])
        self.right_wrist_pose[:3,3] = np.array([0.2, -0.2, -0.4])
        # Joystick values from controller inputs
        self.right_joystick_x = 0.0
        self.right_joystick_y = 0.0
        self.left_joystick_x = 0.0
        self.left_joystick_y = 0.0

        self.use_fingers = False
        self.converged = False
        
        # Track message timing to detect gaps (unpause)
        self.last_message_time = None
        
        # Initialize IK solver to home position
        self.reset_to_home()
    
    def reset_to_home(self):
        """
        Reset IK solver to home position for better warm start convergence.
        
        Home position (in radians):
        - Right shoulder roll: -10 degrees
        - Right elbow pitch: 90 degrees
        - Left shoulder roll: 10 degrees
        - Left elbow pitch: -90 degrees
        - All other joints: 0
        
        Joint indices in IK solver:
        0: dof_right_shoulder_pitch_03
        1: dof_right_shoulder_roll_03
        2: dof_right_shoulder_yaw_02
        3: dof_right_elbow_02
        4: dof_right_wrist_00
        5: dof_left_shoulder_pitch_03
        6: dof_left_shoulder_roll_03
        7: dof_left_shoulder_yaw_02
        8: dof_left_elbow_02
        9: dof_left_wrist_00
        """
        home_position = np.zeros(10, dtype=np.float32)
        home_position[1] = math.radians(-10.0)  # Right shoulder roll
        home_position[3] = math.radians(90.0)   # Right elbow pitch
        home_position[6] = math.radians(10.0)   # Left shoulder roll
        home_position[8] = math.radians(-90.0)  # Left elbow pitch
        
        # Set the IK solver's last solution to home position
        import jax.numpy as jnp
        self.ik_solver.last_solution = jnp.array(home_position)

    def update_joints(self, side: str, fingers: np.ndarray):
        if side == 'left':
            self.left_finger_poses = fingers
        else:
            self.right_finger_poses = fingers
        self.use_fingers = True

    def update_target_location(self, side: str, pose: np.ndarray):
        if side == 'left':
            self.left_wrist_pose = pose
        else:
            self.right_wrist_pose = pose

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
        """
        Check time between messages and reset converged flag if gap > 0.5s.
        The IK solver uses the previous solution as a warm start, so it needs time to converge if the position jumps.
        """
        current_time = time.time()
        
        if self.last_message_time is not None:
            time_delta = current_time - self.last_message_time
            
            if time_delta >= 0.5:
                print(f"Message gap detected: {time_delta:.3f}s - resetting converged flag")
                self.converged = False
        
        self.last_message_time = current_time
    
    def _compute_gripper_from_fingers(self):
        '''
        Map finger spacing to gripper joint positions
        '''
        right_finger_spacing = np.linalg.norm(self.right_finger_poses[8,:3,3] - self.right_finger_poses[3,:3,3])
        right_gripper_joint = 0.068*np.clip(right_finger_spacing/0.15, 0, 1)
        left_finger_spacing = np.linalg.norm(self.left_finger_poses[8,:3,3] - self.left_finger_poses[3,:3,3])
        left_gripper_joint = 0.068*np.clip(left_finger_spacing/0.15, 0, 1)
        return right_gripper_joint, left_gripper_joint
    
    def _compute_gripper_from_controllers(self):
        '''
        Map controller trigger/grip values to gripper joint positions
        '''
        # Map controller trigger/grip values to gripper joint positions
    
        return self.right_gripper_value * 0.9, self.left_gripper_value * 0.9  

    @profile
    async def compute_and_send_joints(self):
        '''
        Peforms IK on left_wrist_pose and right_writst_pose.
        Updates all the commands in the kinfer_command_handler.
        Sends kinematics info back to client, including joint angles and error distance.
        '''
        hand_target_left = self.base_to_head_transform @ self.left_wrist_pose
        hand_target_right = self.base_to_head_transform @ self.right_wrist_pose

        hand_target_left[2, 3] = max(hand_target_left[2, 3], -0.25)
        hand_target_right[2, 3] = max(hand_target_right[2, 3], -0.25)
        
        # Compute inverse kinematics
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

        # Compute actual end effector poses using forward kinematics
        # Combine right and left arm joints (5 each) into the expected 10-element array
        all_joint_angles = np.concatenate([right_arm_joints, left_arm_joints])
        actual_poses = self.ik_solver.forward_kinematics(all_joint_angles)
        
        # Extract actual poses for right and left arms
        actual_right_pose = actual_poses[0]  # First end effector (right arm)
        actual_left_pose = actual_poses[1]   # Second end effector (left arm)
        
        # Calculate distances between target and actual positions
        right_distance = np.linalg.norm(hand_target_right[:3, 3] - actual_right_pose[:3, 3])
        left_distance = np.linalg.norm(hand_target_left[:3, 3] - actual_left_pose[:3, 3])
        
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
        if (right_distance < 0.05 and left_distance < 0.05):
            self.converged = True
        if self.converged:
            self.kinfer_command_handler.update_commands (
                right_arm_joints.tolist() + [right_gripper_joint],
                left_arm_joints.tolist() + [left_gripper_joint],
                (self.right_joystick_x, self.right_joystick_y),
                (self.left_joystick_x, self.left_joystick_y)
                )
            await self.websocket.send(json.dumps(payload))
            self.kinfer_command_handler.send_commands()

        


        

    # def send_kos_commands(self, right_arm: list, left_arm: list):
    #     '''
    #     Takes input in the same format as compute_joint_angles arm output
    #     '''
    #     self.kos_command_handler._send_udp(right_arm, left_arm)