import can, time, argparse
import numpy as np

parser = argparse.ArgumentParser(description='Set finger position via CAN')
parser.add_argument('--finger', type=int, default=1, help='Finger ID (default: 1)')
parser.add_argument('--canbus', type=int, default=0, help='CAN ID (default: 0)')
parser.add_argument('--position', type=float, default=0, help='Position percentage 0-100')
args = parser.parse_args()

# Convert percentage to 0-65535 range
position = int((args.position / 100) * 65535)

bus = can.Bus(interface="socketcan", channel=f"can{args.canbus}", bitrate=1_000_000)


bus.shutdown()

class ROHHands:
    def __init__(self, left_canbus=0, right_canbus=1):
        self.left_bus = can.Bus(interface="socketcan", channel=f"can{left_canbus}", bitrate=1_000_000)
        self.right_bus = can.Bus(interface="socketcan", channel=f"can{right_canbus}", bitrate=1_000_000)

    def _set_hand_joints(self, bus: can.Bus, positions: np.ndarray):
        for finger, position in enumerate(positions):
            data = bytes([finger, position & 0xFF, (position >> 8) & 0xFF, 255])

            HAND_ID = 0x02
            MASTER_ID = 0x01
            cmd = 0x4C 

            fullmsg = bytearray([0x55, 0xAA, HAND_ID, MASTER_ID, cmd, len(data)])
            fullmsg.extend(data)

            l = 0
            tempFullmsg = fullmsg.copy()
            tempFullmsg = tempFullmsg + b"\x00"

            for b in tempFullmsg[2:-1]:
                l ^= b
            crcbyte = l & 0xFF

            fullmsg.append(crcbyte)
            fullmsg = bytes(fullmsg)

            for i in range(0, len(fullmsg), 8):
                chunk = fullmsg[i:i+8]
                msg = can.Message(arbitration_id=0x02, is_extended_id=False, data=chunk)
                bus.send(msg)
    
    def set_left_hand_joints(self, positions: np.ndarray):
        self._set_hand_joints(self.left_bus, positions)

    def set_right_hand_joints(self, positions: np.ndarray):
        self._set_hand_joints(self.right_bus, positions)
