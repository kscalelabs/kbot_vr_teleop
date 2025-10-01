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
    
    def build_commands(self, right_arm_angles, left_arm_angles, right_joystick, left_joystick):
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

        new_commands = [right_joystick[1], right_joystick[0], left_joystick[0], 0, 0, 0]
        new_commands += [
            right_arm_angles[0],
            right_arm_angles[1],
            right_arm_angles[2],
            right_arm_angles[3],
            right_arm_angles[4],
        ]
        if right_gripper is not None:
            new_commands += [float(right_gripper)]
        new_commands += [
            left_arm_angles[0],
            left_arm_angles[1],
            left_arm_angles[2],
            left_arm_angles[3],
            left_arm_angles[4],
        ]
        if left_gripper is not None:
            new_commands += [float(left_gripper)]
        return (json.dumps({"commands": new_commands}) + "\n").encode("utf-8")

    def send_commands(self, right_arm_angles, left_arm_angles, right_joystick, left_joystick):
        new_commands = self.build_commands(right_arm_angles, left_arm_angles, right_joystick, left_joystick)
        self.sock.sendto(new_commands, (self.UDP_IP, self.UDP_PORT)) 