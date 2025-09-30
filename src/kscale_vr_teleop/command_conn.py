import json
import socket
import math
from dataclasses import dataclass
import numpy as np

class Commander16:
    def __init__(self, udp_ip: str = "localhost", udp_port: int = 10000):
        self.UDP_IP = udp_ip
        self.UDP_PORT = udp_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    def build_commands(self, right_arm_angles, left_arm_angles):
        left_gripper = None
        if len(left_arm_angles) > 5:
            # Map 0-1 input to -25° to +25° radians with left gripper offset
            input_val = float(left_arm_angles[5])
            gripper_range_min = math.radians(-25)   # radians (fully open)
            gripper_range_max = math.radians(25.0)  # radians (fully closed)
            offset = math.radians(-8)  # Left grippers offset
            mapped_value = gripper_range_max - input_val * (gripper_range_max - gripper_range_min)
            left_gripper = mapped_value + offset
        right_gripper = None

        if len(right_arm_angles) > 5:
            # Map 0-1 input to -25° to +25° radians with right gripper offset
            input_val = float(right_arm_angles[5])
            gripper_range_min = math.radians(-25)   # radians (fully open)
            gripper_range_max = math.radians(25.0)  # radians (fully closed)
            offset = math.radians(-25)  # Right gripper offset
            mapped_value = gripper_range_max - input_val * (gripper_range_max - gripper_range_min)
            right_gripper = mapped_value + offset

        new_commands = {
            "LShoulderPitch": float(left_arm_angles[0]),
            "LShoulderRoll": float(left_arm_angles[1]),
            "LElbowPitch": float(left_arm_angles[2]),
            "LElbowRoll": float(left_arm_angles[3]),
            "LWristRoll": float(left_arm_angles[4]),
            "LWristGripper": float(left_gripper),
            
            "RShoulderPitch": float(right_arm_angles[0]),
            "RShoulderRoll": float(right_arm_angles[1]),
            "RElbowPitch": float(right_arm_angles[2]),
            "RElbowRoll": float(right_arm_angles[3]),
            "RWristRoll": float(right_arm_angles[4]),
            "RWristGripper": float(right_gripper),
        }
        if left_gripper is None:
            del new_commands["LWristGripper"]
        if right_gripper is None:
            del new_commands["RWristGripper"]
        return (json.dumps(new_commands) + "\n").encode("utf-8")

    def send_commands(self, right_arm_angles, left_arm_angles):
        new_commands = self.build_commands(right_arm_angles, left_arm_angles)
        self.sock.sendto(new_commands, (self.UDP_IP, self.UDP_PORT)) 