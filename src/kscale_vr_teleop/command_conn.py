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
    
    def add_joint_bias(self, commands):
        commands["rshoulderroll"] += math.radians(-10.0)
        commands["relbowroll"] += math.radians(90.0)
        commands["rwristgripper"] += math.radians(-8.0)
        commands["lshoulderroll"] += math.radians(10.0)
        commands["lelbowroll"] += math.radians(-90.0)
        commands["lwristgripper"] += math.radians(-25.0)
        return commands
        
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

        new_commands = {
            "xvel": right_joystick[1], # pushing up or down on right joystick is "X" axis for policies
            "yvel": right_joystick[0],
            "yaw": left_joystick[0],
            "baseheight":0,
            "baseroll": 0,
            "basepitch": 0,
            "rshoulderpitch": right_arm_angles[0],
            "rshoulderroll": right_arm_angles[1],
            "relbowpitch": right_arm_angles[2],  
            "relbowroll": right_arm_angles[3],  
            "rwristroll": right_arm_angles[4], 
            "rwristgripper": right_gripper,  
            "lshoulderpitch": left_arm_angles[0],  
            "lshoulderroll": left_arm_angles[1],  
            "lelbowpitch": left_arm_angles[2],  
            "lelbowroll": left_arm_angles[3],  
            "lwristroll": left_arm_angles[4],  
            "lwristgripper": left_gripper,  
        }



        return (json.dumps({"commands": self.add_joint_bias(new_commands)}) + "\n").encode("utf-8")

    def send_commands(self, right_arm_angles, left_arm_angles, right_joystick, left_joystick):
        new_commands = self.build_commands(right_arm_angles, left_arm_angles, right_joystick, left_joystick)
        print(new_commands)
        self.sock.sendto(new_commands, (self.UDP_IP, self.UDP_PORT)) 