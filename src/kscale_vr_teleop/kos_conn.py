import pykos
import numpy as np


class KOSHandler:
    def __init__(self):
        # Create KOS client directly (sync API)
        self.kos_client = pykos.KOS()

        # Configure all actuators for control
        for joint_id in self.all_joint_ids:
            # Configure for control (like test_pykos_fixed.py)
            self.kos_client.actuator.configure_actuator(
                actuator_id=joint_id,
                kp=10,  # Position gain (reduced from 150)
                kd=1,   # Velocity gain (reduced from 10)
                torque_enabled=True  # Enable torque control
            )

    def send_commands(self, right_arm_angles, left_arm_angles):
        actuator_commands = [
            {'actuator_id': "11", 'position': float(left_arm_angles[0])},
            {'actuator_id': "12", 'position': float(left_arm_angles[1])},
            {'actuator_id': "13", 'position': float(left_arm_angles[2])},
            {'actuator_id': "14", 'position': float(left_arm_angles[3])},
            {'actuator_id': "15", 'position': float(left_arm_angles[4])},
            {'actuator_id': "21", 'position': float(right_arm_angles[0])},
            {'actuator_id': "22", 'position': float(right_arm_angles[1])},
            {'actuator_id': "23", 'position': float(right_arm_angles[2])},
            {'actuator_id': "24", 'position': float(right_arm_angles[3])},
            {'actuator_id': "25", 'position': float(right_arm_angles[4])}
        ]

        self.kos_client.actuator.command_actuators(actuator_commands)