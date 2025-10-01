#!/usr/bin/env python3
"""
Standalone rerun visualizer that receives robot joint positions over UDP.

Usage:
    python rerun.py [--port PORT] [--host HOST]

Expected UDP message format (JSON):
    {"commands": [leg_joints(6), right_arm(5), right_gripper, left_arm(5), left_gripper]}
    OR
    {"joint_angles": {"joint_name": angle, ...}}
"""

import argparse
import json
import socket
import time
from pathlib import Path

import numpy as np
import rerun as rr

from kscale_vr_teleop._assets import ASSETS_DIR
from kscale_vr_teleop.analysis.rerun_loader_urdf import URDFLogger


class RerunUDPVisualizer:
    def __init__(self, urdf_path: str, host: str = "0.0.0.0", port: int = 10000):
        """
        Initialize the Rerun visualizer with UDP socket.
        
        Args:
            urdf_path: Path to the robot URDF file
            host: UDP host to bind to (default: "0.0.0.0" for all interfaces)
            port: UDP port to listen on (default: 10002)
        """
        self.urdf_path = urdf_path
        self.host = host
        self.port = port
        
        # Initialize Rerun
        logs_folder = Path(f'~/.vr_teleop_logs/{time.strftime("%Y-%m-%d")}/').expanduser()
        logs_folder.mkdir(parents=True, exist_ok=True)
        logs_path = logs_folder / f'udp_replay_{time.strftime("%H-%M-%S")}.rrd'
        
        rr.init("udp_robot_visualizer")
        print(f"Saving logs to {logs_path}")
        rr.save(logs_path)
        rr.spawn()
        
        # Set up coordinate system
        rr.log('origin_axes', rr.Transform3D(translation=[0, 0, 0], axis_length=0.1), static=True)
        
        # Initialize URDF logger
        self.urdf_logger = URDFLogger(urdf_path, root_path="robot")
        
        # Log initial robot pose
        self.urdf_logger.log()
        
        # Create UDP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.settimeout(0.1)  # 100ms timeout for graceful shutdown
        
        print(f"UDP socket listening on {self.host}:{self.port}")
        print("Waiting for robot joint positions...")
        
        # Joint name mapping (indices 6-15 of incoming array)
        # Order from pyfirmware udp_listener.py:
        # [6-10]: RShoulderPitch, RShoulderRoll, RElbowPitch, RElbowRoll, RWristRoll
        # [11-15]: LShoulderPitch, LShoulderRoll, LElbowPitch, LElbowRoll, LWristRoll
        self.joint_names = [
            'dof_right_shoulder_pitch_03',  # Index 6
            'dof_right_shoulder_roll_03', 
            'dof_right_shoulder_yaw_02',   # Index 7
            'dof_right_elbow_02',            # Index 8
            'dof_right_wrist_00',            # Index 10
            'dof_left_shoulder_pitch_03',   # Index 11
            'dof_left_shoulder_roll_03',  
            'dof_left_shoulder_yaw_02',   # Index 12
            'dof_left_elbow_02',             # Index 13    # Index 14 (was LElbowRoll)
            'dof_left_wrist_00',             # Index 15
        ]
        
        print("Ready to receive messages in format:")
        print("  [base_joints(6), right_arm(5), left_arm(5)]")
        print("  (First 6 indices will be ignored)")
    
    def _parse_message(self, message: dict) -> dict:
        """
        Parse incoming message and convert to joint_angles dictionary.
        
        Supports two formats:
        1. Array format: [base(6), right_arm(5), left_arm(5)]
        2. Dictionary format: {"joint_angles": {...}}
        """
        # Check if it's already in joint_angles dictionary format
        if "joint_angles" in message:
            return message["joint_angles"]
        
        # Check if it's in array format (direct list or under "commands" key)
        commands = None
        if isinstance(message, list):
            commands = message
        elif "commands" in message:
            commands = message["commands"]
        
        if commands is None:
            print(f"Unknown message format: {message.keys() if isinstance(message, dict) else type(message)}")
            return {}
        
        # Parse array format: skip first 6, then map to joint names
        if len(commands) < 16:
            print(f"Warning: Expected at least 16 values, got {len(commands)}")
            return {}
        joint_angles = {}
        # Map indices 6-15 to joint names
        for i, joint_name in enumerate(self.joint_names):
            array_idx = 6 + i
            if array_idx < len(commands):
                joint_angles[joint_name] = float(commands[array_idx])
        
        return joint_angles
    
    def run(self):
        """Main loop to receive and visualize UDP messages."""
        message_count = 0
        last_print_time = time.time()
        
        try:
            while True:
                try:
                    # Receive UDP message
                    data, addr = self.sock.recvfrom(4096)
                    message = json.loads(data.decode('utf-8'))
                    print(message)
                    # Parse joint angles from message
                    joint_angles = self._parse_message(message)
                    
                    # Log to rerun
                    if joint_angles:
                        # Set timestamp
                        # Update robot visualization
                        self.urdf_logger.log(joint_angles)
                        
                        message_count += 1
                        
                        # Print status every second
                        current_time = time.time()
                        if current_time - last_print_time >= 1.0:
                            print(f"Received {message_count} messages (rate: {message_count:.1f} msg/s)")
                            message_count = 0
                            last_print_time = current_time
                
                except socket.timeout:
                    # Timeout is expected, continue waiting
                    continue
                except json.JSONDecodeError as e:
                    print(f"Failed to parse JSON: {e}")
                    continue
                except Exception as e:
                    print(f"Error processing message: {e}")
                    continue
        
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.sock.close()
            print("UDP socket closed")


def main():    
    urdf_path = str(ASSETS_DIR / "kbot_legless" / "robot.urdf")
    print(f"Using URDF: {urdf_path}")
    
    # Create and run visualizer
    visualizer = RerunUDPVisualizer(urdf_path)
    visualizer.run()


if __name__ == "__main__":
    main()

