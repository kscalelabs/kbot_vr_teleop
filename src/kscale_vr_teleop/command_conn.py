import json
import socket
import math
from dataclasses import dataclass
import numpy as np


@dataclass
class ControlVector16:
    # 0..2 base velocities
    XVel: float = 0.0
    YVel: float = 0.0
    YawRate: float = 0.0

    # 3..5 base pose
    BaseHeight: float = 0.0
    BaseRoll: float = 0.0
    BasePitch: float = 0.0

    # 6..10 right arm
    RShoulderPitch: float = 0.0
    RShoulderRoll: float = 0.0
    RElbowPitch: float = 0.0
    RElbowRoll: float = 0.0
    RWristRoll: float = 0.0
    RWristGripper: float = 0.0

    # 11..15 left arm
    LShoulderPitch: float = 0.0
    LShoulderRoll: float = 0.0
    LElbowPitch: float = 0.0
    LElbowRoll: float = 0.0
    LWristRoll: float = 0.0
    LWristGripper: float = 0.0


    def to_msg(self) -> bytes:
        # Keep the same JSON keys expected by firmware (serde rename fields)
        payload = {
            "XVel": self.XVel,
            "YVel": self.YVel,
            "YawRate": self.YawRate,
            "BaseHeight": self.BaseHeight,
            "BaseRoll": self.BaseRoll,
            "BasePitch": self.BasePitch,
            "RShoulderPitch": self.RShoulderPitch,
            "RShoulderRoll": self.RShoulderRoll,
            "RElbowPitch": self.RElbowPitch,
            "RElbowRoll": self.RElbowRoll,
            "RWristRoll": self.RWristRoll,
            "RWristGripper": self.RWristGripper,
            "LShoulderPitch": self.LShoulderPitch,
            "LShoulderRoll": self.LShoulderRoll,
            "LElbowPitch": self.LElbowPitch,
            "LElbowRoll": self.LElbowRoll,
            "LWristRoll": self.LWristRoll,
            "LWristGripper": self.LWristGripper,
        }
        return (json.dumps(payload) + "\n").encode("utf-8")


class Commander16:
    def __init__(self, udp_ip: str = "localhost", udp_port: int = 10000):
        self.UDP_IP = udp_ip
        self.UDP_PORT = udp_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.max_cmd = 0.5
        self._ultimate_max = 1.5
        self._ultimate_min = 0.1
        self.cmds = ControlVector16()

    def send_commands(self, right_arm_angles, left_arm_angles):
        self.cmds.LShoulderPitch = float(left_arm_angles[0])
        self.cmds.LShoulderRoll = float(left_arm_angles[1])
        self.cmds.LElbowPitch = float(left_arm_angles[2])
        self.cmds.LElbowRoll = float(left_arm_angles[3])
        self.cmds.LWristRoll = float(left_arm_angles[4])
        if len(left_arm_angles) > 5:
            # Map 0-1 input to -25° to +25° radians with left gripper offset
            input_val = float(left_arm_angles[5])
            gripper_range_min = math.radians(-25)   # radians (fully open)
            gripper_range_max = math.radians(25.0)  # radians (fully closed)
            offset = math.radians(-8)  # Left gripper offset
            mapped_value = gripper_range_max - input_val * (gripper_range_max - gripper_range_min)
            self.cmds.LWristGripper = mapped_value + offset
            
        self.cmds.RShoulderPitch = float(right_arm_angles[0])
        self.cmds.RShoulderRoll = float(right_arm_angles[1])
        self.cmds.RElbowPitch = float(right_arm_angles[2])
        self.cmds.RElbowRoll = float(right_arm_angles[3])
        self.cmds.RWristRoll = float(right_arm_angles[4])
        if len(right_arm_angles) > 5:
            # Map 0-1 input to -25° to +25° radians with right gripper offset
            input_val = float(right_arm_angles[5])
            gripper_range_min = math.radians(-25)   # radians (fully open)
            gripper_range_max = math.radians(25.0)  # radians (fully closed)
            offset = math.radians(-25)  # Right gripper offset
            mapped_value = gripper_range_max - input_val * (gripper_range_max - gripper_range_min)
            self.cmds.RWristGripper = mapped_value + offset
            
        self.sock.sendto(self.cmds.to_msg(), (self.UDP_IP, self.UDP_PORT)) # This line takes a non-trivial amount of time (8e-4s on a *desktop*)

if __name__ == "__main__":
    cmdr = Commander16()
    import time

    start = time.time()
    while True:
        t = time.time() - start
        zero_to_one_sine = 0.5*(1+np.sin(t))
        # cmdr.send_commands(np.deg2rad([0, -20, 0, 80 + 20*zero_to_one_sine, 0]).tolist()+ [gripper_pos], np.deg2rad([0, 20, 0, -80, 0]).tolist()+ [gripper_pos])
        cmdr.send_commands(np.deg2rad([0, -20, 0, 90, -45+90*zero_to_one_sine]).tolist(), np.deg2rad([0, 20, 0, -90, 0]).tolist())
        print(f"Sent command at t={t:.2f}s, sine={zero_to_one_sine}", end='\r')
        time.sleep(0.01)