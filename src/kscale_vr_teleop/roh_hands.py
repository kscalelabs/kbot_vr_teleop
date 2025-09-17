import can, time
import numpy as np

class ROHHands:
    def __init__(self, left_canbus=3, right_canbus=2):
        self.left_bus = can.Bus(interface="socketcan", channel=f"can{left_canbus}", bitrate=1_000_000)
        self.right_bus = can.Bus(interface="socketcan", channel=f"can{right_canbus}", bitrate=1_000_000)

    def _set_hand_joints(self, bus: can.Bus, positions: np.ndarray):
        for finger, position in enumerate(positions):
            position_scaled = int((position / 100) * 65535)
            data = bytes([finger, position_scaled & 0xFF, (position_scaled >> 8) & 0xFF, 255])

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


    def __del__(self):
        self.left_bus.shutdown()
        self.right_bus.shutdown()

if __name__ == "__main__":
    # make sine waves and send to hand
    roh = ROHHands()
    while True:
        time_ms = int(round(time.time() * 1000))
        pos = (np.sin(time_ms / 1000) + 1) / 2 * 100
        positions = np.array([pos, pos, pos, pos, pos, pos])
        roh.set_left_hand_joints(positions)
        roh.set_right_hand_joints(positions)
        time.sleep(1/40)