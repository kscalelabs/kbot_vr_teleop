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
        self.cmds = {
            "xvel": 0, # pushing up or down on right joystick is "X" axis for policies
            "yvel": 0,
            "yawrate": 0,
            "baseheight":0,
            "baseroll": 0,
            "basepitch": 0,
            "rshoulderpitch": 0,
            "rshoulderroll": 0,
            "rshoulderyaw": 0,  
            "relbowpitch": 0,  
            "rwristroll": 0, 
            "rwristgripper": 0,  
            "lshoulderpitch": 0,  
            "lshoulderroll": 0,  
            "lshoulderyaw": 0,  
            "lelbowpitch": 0,  
            "lwristroll": 0,  
            "lwristgripper": 0,  
        }
    
    def add_joint_bias(self, commands):
        commands["rshoulderroll"] += math.radians(10.0)
        commands["relbowpitch"] += math.radians(-90.0)
        commands["rwristgripper"] += math.radians(-8.0)
        commands["lshoulderroll"] += math.radians(-10.0)
        commands["lelbowpitch"] += math.radians(90.0)
        commands["lwristgripper"] += math.radians(-25.0)          
        return commands
        
    def update_commands(self, right_arm_angles, left_arm_angles, right_joystick, left_joystick):
        self.cmds = {
            "xvel": right_joystick[1], # pushing up or down on right joystick is "X" axis for policies
            "yvel": -right_joystick[0], 
            "yawrate": -left_joystick[0],
            "baseheight":0,
            "baseroll": 0,
            "basepitch": 0,
            "rshoulderpitch": right_arm_angles[0],
            "rshoulderroll": right_arm_angles[1],
            "rshoulderyaw": right_arm_angles[2],  
            "relbowpitch": right_arm_angles[3],  
            "rwristroll": right_arm_angles[4], 
            "rwristgripper": right_arm_angles[5],  
            "lshoulderpitch": left_arm_angles[0],  
            "lshoulderroll": left_arm_angles[1],  
            "lshoulderyaw": left_arm_angles[2],  
            "lelbowpitch": left_arm_angles[3],  
            "lwristroll": left_arm_angles[4],  
            "lwristgripper": left_arm_angles[5],  
        }

    def send_commands(self):
        new_commands =  (json.dumps({"commands": self.add_joint_bias(self.cmds)}) + "\n").encode("utf-8")
        print(new_commands)
        self.sock.sendto(new_commands, (self.UDP_IP, self.UDP_PORT)) 