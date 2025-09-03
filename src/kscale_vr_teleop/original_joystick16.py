import json
import socket
from dataclasses import dataclass
import time
import threading


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
    RShoulderPitch: float = 0.2
    RShoulderRoll: float = 0.0
    RElbowPitch: float = 0.0
    RElbowRoll: float = 0.0
    RWristPitch: float = 0.0

    # 11..15 left arm
    LShoulderPitch: float = -0.1
    LShoulderRoll: float = 0.0
    LElbowPitch: float = 0.0
    LElbowRoll: float = 0.0
    LWristPitch: float = 0.0

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
            "RWristPitch": self.RWristPitch,
            "LShoulderPitch": self.LShoulderPitch,
            "LShoulderRoll": self.LShoulderRoll,
            "LElbowPitch": self.LElbowPitch,
            "LElbowRoll": self.LElbowRoll,
            "LWristPitch": self.LWristPitch,
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

    def increase_max_cmd(self) -> None:
        self.max_cmd = min(self.max_cmd + 0.1, self._ultimate_max)

    def decrease_max_cmd(self) -> None:
        self.max_cmd = max(self.max_cmd - 0.1, self._ultimate_min)

        self.cmds = ControlVector16()

    def send(self) -> None:
        self.sock.sendto(self.cmds.to_msg(), (self.UDP_IP, self.UDP_PORT))


class CommandDisplay16:
    def __init__(self, udp_ip: str = "localhost", udp_port: int = 10000):
        self.commander: Commander16 = Commander16(udp_ip, udp_port)

    def run(self):
        thread = threading.Thread(target=self.controller_thread, daemon=True)
        thread.start()
        try:
            while thread.is_alive():
                self.commander.update_from_controller(self.controller)
                self.commander.send()
                time.sleep(0.05)  # 20 Hz
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    CommandDisplay16().run()