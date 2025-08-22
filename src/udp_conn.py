import time
import numpy as np
import socket
import json



class UDPHandler:
    def __init__(self, udp_host, udp_port):
        self.udp_host = udp_host
        self.udp_port = udp_port
        self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp_sock.setblocking(False)

        # Increase send buffer size to handle bursts
        self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)  # 64KB

        # Set socket priority (if supported)
        try:
            self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_PRIORITY, 6)  # High priority
        except:
            pass  # Not all systems support this
        # Enable broadcast (useful for some network setups)
        self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    def _send_udp(self, right_arm_angles, left_arm_angles, right_finger_angles, left_finger_angles):
        # finger was 0 to 65535 because of the glove format
        # Joint Mapping:
        # 11: Left shoulder pitch (inverted)
        # 12: Left shoulder roll
        # 13: Left shoulder yaw
        # 14: Left elbow
        # 15: Left wrist (inverted)
        # 21: Right shoulder pitch (inverted)
        # 22: Right shoulder roll
        # 23: Right shoulder yaw
        # 24: Right elbow
        # 25: Right wrist (inverted)
        # fingers
        # Type: Array of 6 integers
        # Range: 0-65535 (16-bit values)
        # Index Mapping:
        # [0]: Thumb
        # [1]: Index finger
        # [2]: Middle finger
        # [3]: Ring finger
        # [4]: Pinky
        # [5]: thumb extra joint
        left_arm_angles =  np.zeros(5)
        right_arm_angles = np.zeros(5)
        payload = {
            "timestamp": time.time(),
            "joints": {
                "11": -left_arm_angles[0],
                "12": left_arm_angles[1],
                "13": left_arm_angles[2],
                "14": left_arm_angles[3],
                "15": left_arm_angles[4],
                "21": right_arm_angles[0],
                "22": right_arm_angles[1],
                "23": right_arm_angles[2],
                "24": right_arm_angles[3],
                "25": right_arm_angles[4]
            },
            # thumb: -0.2, 1
            # other fingers: -2.3, 1
            "fingers": np.clip(right_finger_angles * (65535 / (2*np.pi)), 0, 65535).astype(int).tolist()
        }
        print(payload)
        try:
            self._udp_sock.sendto(json.dumps(payload).encode("utf-8"), (self.udp_host, self.udp_port))
        except Exception:
            # Avoid blocking/logging in hot path
            pass