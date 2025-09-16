import socket
import json
import numpy as np
from kscale_vr_teleop.roh_hands import ROHHands
import rerun as rr
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FingerUDPListener:
    """UDP listener class for finger joint angles. 
    """
    def __init__(self, udp_host: str = '0.0.0.0', udp_port: int = 10001):
        """
        Initialize UDP listener for receiving finger joint angles on the robot.
        Args:
            udp_host (str): Host IP to bind (default: 0.0.0.0 for all interfaces).
            udp_port (int): UDP port for finger commands (default: 10001).
        """
        self.udp_host = udp_host
        self.udp_port = udp_port
        self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp_sock.setblocking(False)
        self._udp_sock.bind((self.udp_host, self.udp_port))

        # Initialize ROHHands for CAN communication
        self.roh_hands = ROHHands()

    def process_packet(self) -> bool:
        """
        Receive and process a single UDP packet, sending finger angles to ROHHands.
        
        Returns: True if a packet was processed, False if no packet available.
        """
        try:
            data, _ = self._udp_sock.recvfrom(1024)  # Buffer size 1024 bytes
            payload = json.loads(data.decode('utf-8'))
            
            # Extract finger angles (6 per hand, 0-1)
            right_fingers = np.array(payload.get('right_fingers', [0]*6), dtype=np.float32)
            left_fingers = np.array(payload.get('left_fingers', [0]*6), dtype=np.float32)

            # Validate 6 angles per hand
            if right_fingers.shape != (6,) or left_fingers.shape != (6,):
                logger.error(f"Invalid finger angle shape: right={right_fingers.shape}, left={left_fingers.shape}")
                return True

            # Send to ROHHands (scale 0-1 to 0-100 for CAN)
            self.roh_hands.set_right_hand_joints(right_fingers * 100)
            self.roh_hands.set_left_hand_joints(left_fingers * 100)
            return True

        except socket.error:
            return False  # No packet available
        except json.JSONDecodeError:
            logger.error("Invalid JSON in UDP packet")
            return True
        except Exception as e:
            logger.error(f"Error processing UDP packet: {e}")
            return True

    def run(self) -> None:
        """
        Main loop to continuously process incoming UDP packets.
        """
        logger.info(f"Finger UDP listener started on {self.udp_host}:{self.udp_port}")
        while True:
            self.process_packet()

if __name__ == "__main__":
    listener = FingerUDPListener()
    listener.run()
