import socket
import json
import time
import numpy as np

class FingerUDPHandler:
    def __init__(self, udp_host, udp_port=10001):
        """
        Initialize UDP handler for sending finger joint angles to robot.
        Args:
            udp_host (str): Robot IP address
            udp_port (int): UDP port for finger commands (default: 10001).
        """
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

    def send_finger_commands(self, right_fingers, left_fingers):
        """
        Send finger joint angles to robot via UDP.
        Args:
            right_fingers (np.ndarray): 6 angles (thumb_metacarpal, thumb, index, middle, ring, pinky), 0-1.
            left_fingers (np.ndarray): 6 angles, same order, 0-1.
        """
        # Ensure inputs are numpy arrays, clipped to 0-1
        right_fingers = np.clip(np.array(right_fingers, dtype=np.float32), 0, 1)
        left_fingers = np.clip(np.array(left_fingers, dtype=np.float32), 0, 1)

        # Construct payload
        payload = {
            "timestamp": time.time(),
            "right_fingers": right_fingers.tolist(),
            "left_fingers": left_fingers.tolist()
        }

        try:
            self._udp_sock.sendto(json.dumps(payload).encode("utf-8"), (self.udp_host, self.udp_port))
        except Exception:
            print("Failed to send udp packet")