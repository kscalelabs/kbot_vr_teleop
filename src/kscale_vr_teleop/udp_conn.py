import time
import numpy as np
import socket
import json
import rerun as rr
from scipy.spatial.transform import Rotation


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
        payload = {
            "timestamp": time.time(),
            "joints": {
                "11": -left_arm_angles[0],
                "12": left_arm_angles[1],
                "13": left_arm_angles[2],
                "14": left_arm_angles[3],
                "15": left_arm_angles[4],
                "21": np.rad2deg(right_arm_angles[0]),
                "22": np.rad2deg(right_arm_angles[1]),
                "23": np.rad2deg(right_arm_angles[2]),
                "24": np.rad2deg(right_arm_angles[3]),
                "25": np.rad2deg(right_arm_angles[4])
            },
            "fingers": (np.clip(65535-right_finger_angles * 65535, 0, 65535).astype(int)).tolist()
        }
        # loop through keys recursively and log rerun scalars for each leaf node
        def log_rerun_scalars(data, parent_key=""):
            if isinstance(data, dict):
                for key, value in data.items():
                    log_rerun_scalars(value, parent_key=f"{parent_key}.{key}" if parent_key else key)
            else:
                rr.log(parent_key, rr.Scalar(data), static=True)

        log_rerun_scalars(payload)

        try:
            self._udp_sock.sendto(json.dumps(payload).encode("utf-8"), (self.udp_host, self.udp_port))
        except Exception:
            # Avoid blocking/logging in hot path
            pass

class RLUDPHandler:
    def __init__(self, udp_host):
        self.udp_host = udp_host
        self.udp_port = 1234
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

    def _send_udp(self, left_wrist_mat, right_wrist_mat):
        payload = {
            "velocity": np.zeros(3, dtype=np.float32).tolist(),
            "left_ee": [*left_wrist_mat[:3, 3], *Rotation.from_matrix(left_wrist_mat[:3, :3]).as_quat()],
            "right_ee": [*right_wrist_mat[:3, 3], *Rotation.from_matrix(right_wrist_mat[:3, :3]).as_quat()]
        }
        # loop through keys recursively and log rerun scalars for each leaf node
        def log_rerun_scalars(data, parent_key=""):
            if isinstance(data, dict):
                for key, value in data.items():
                    log_rerun_scalars(value, parent_key=f"{parent_key}.{key}" if parent_key else key)
            else:
                rr.log(parent_key, rr.Scalar(data), static=True)

        log_rerun_scalars(payload)

        try:
            self._udp_sock.sendto(json.dumps(payload).encode("utf-8"), (self.udp_host, self.udp_port))
        except Exception:
            # Avoid blocking/logging in hot path
            pass