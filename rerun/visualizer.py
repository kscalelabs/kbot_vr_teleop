#!/usr/bin/env python3
"""
Standalone Rerun visualizer that receives robot joint positions over UDP.

This is a completely optional visualization tool that listens to the same
UDP commands being sent to the robot. It provides real-time 3D visualization
of robot kinematics without affecting the main teleop loop.

Usage:
    python visualizer.py [--port PORT] [--host HOST]

Expected UDP message format (JSON):
    {"commands": {"joint_name": value, ...}}
    
The visualizer receives the exact same commands as the robot, providing
a clear debugging interface with no coupling to the main teleop code.
"""

import argparse
import json
import socket
import sys
import time
from pathlib import Path

import numpy as np
import rerun as rr

# Import from the main package
try:
    from kscale_vr_teleop._assets import ASSETS_DIR
    from kscale_vr_teleop.analysis.rerun_loader_urdf import URDFLogger
except ImportError:
    print("Error: Could not import from kscale_vr_teleop package.")
    print("Make sure the package is installed: pip install -e .")
    sys.exit(1)


class RerunUDPVisualizer:
    def __init__(self, urdf_path: str, host: str = "0.0.0.0", port: int = 10002):
        """
        Initialize the Rerun visualizer with UDP socket.
        
        Args:
            urdf_path: Path to the robot URDF file
            host: UDP host to bind to (default: "0.0.0.0" for all interfaces)
            port: UDP port to listen on (default: 10002 to avoid conflicts)
        """
        self.urdf_path = urdf_path
        self.host = host
        self.port = port
        
        # Initialize Rerun
        logs_folder = Path(f'~/.vr_teleop_logs/{time.strftime("%Y-%m-%d")}/').expanduser()
        logs_folder.mkdir(parents=True, exist_ok=True)
        logs_path = logs_folder / f'rerun_viz_{time.strftime("%H-%M-%S")}.rrd'
        
        rr.init("vr_teleop_visualizer")
        print(f"Saving logs to {logs_path}")
        rr.save(logs_path)
        rr.spawn()
        
        # Set up coordinate system
        rr.log('origin', rr.Transform3D(translation=[0, 0, 0], axis_length=0.1), static=True)
        
        # Set up timeseries plots
        rr.log("plots/gripper_positions", rr.SeriesLine(color=[255, 0, 0], name="Right Gripper"), static=True)
        rr.log("plots/gripper_positions", rr.SeriesLine(color=[0, 0, 255], name="Left Gripper"), static=True)
        
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
        print("Waiting for robot joint commands...")
        
    def _parse_message(self, message: dict) -> dict:
        """
        Parse incoming message and extract joint angles.
        
        Expected format from command_conn.py:
        {
            "commands": {
                "xvel": 0,
                "yvel": 0,
                ...
                "rshoulderpitch": value,
                "rshoulderroll": value,
                ...
            }
        }
        """
        if "commands" not in message:
            return {}
            
        commands = message["commands"]
        
        # Map command keys to URDF joint names
        joint_mapping = {
            "rshoulderpitch": "dof_right_shoulder_pitch_03",
            "rshoulderroll": "dof_right_shoulder_roll_03",
            "rshoulderyaw": "dof_right_shoulder_yaw_02",
            "relbowpitch": "dof_right_elbow_02",
            "rwristroll": "dof_right_wrist_00",
            "lshoulderpitch": "dof_left_shoulder_pitch_03",
            "lshoulderroll": "dof_left_shoulder_roll_03",
            "lshoulderyaw": "dof_left_shoulder_yaw_02",
            "lelbowpitch": "dof_left_elbow_02",
            "lwristroll": "dof_left_wrist_00",
        }
        
        joint_angles = {}
        for cmd_key, urdf_joint in joint_mapping.items():
            if cmd_key in commands:
                joint_angles[urdf_joint] = float(commands[cmd_key])
        
        # Log gripper values if available
        if "rwristgripper" in commands:
            rr.log("plots/gripper_positions/Right Gripper", rr.Scalar(commands["rwristgripper"]))
        if "lwristgripper" in commands:
            rr.log("plots/gripper_positions/Left Gripper", rr.Scalar(commands["lwristgripper"]))
            
        return joint_angles
    
    def run(self):
        """Main loop to receive and visualize UDP messages."""
        message_count = 0
        last_print_time = time.time()
        
        try:
            print("\n" + "="*60)
            print("Rerun Visualizer Running")
            print("="*60)
            print(f"Listening on: {self.host}:{self.port}")
            print("Send UDP commands in JSON format with 'commands' key")
            print("Press Ctrl+C to stop")
            print("="*60 + "\n")
            
            while True:
                try:
                    # Receive UDP message
                    data, addr = self.sock.recvfrom(4096)
                    message = json.loads(data.decode('utf-8'))
                    
                    # Parse joint angles from message
                    joint_angles = self._parse_message(message)
                    
                    # Log to rerun
                    if joint_angles:
                        self.urdf_logger.log(joint_angles)
                        message_count += 1
                        
                        # Print status every second
                        current_time = time.time()
                        if current_time - last_print_time >= 1.0:
                            fps = message_count / (current_time - last_print_time)
                            print(f"📊 Receiving: {fps:.1f} msg/s | Total: {message_count}")
                            message_count = 0
                            last_print_time = current_time
                
                except socket.timeout:
                    # Timeout is expected, continue waiting
                    continue
                except json.JSONDecodeError as e:
                    print(f"❌ Failed to parse JSON: {e}")
                    continue
                except Exception as e:
                    print(f"⚠️  Error processing message: {e}")
                    continue
        
        except KeyboardInterrupt:
            print("\n\n" + "="*60)
            print("Shutting down Rerun Visualizer...")
            print("="*60)
        finally:
            self.sock.close()
            print("✓ UDP socket closed")


def main():
    parser = argparse.ArgumentParser(
        description="Rerun visualizer for VR teleop robot commands",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Listen on default port 10002
  python visualizer.py
  
  # Listen on custom port
  python visualizer.py --port 10000
  
  # Listen on specific host
  python visualizer.py --host 192.168.1.100 --port 10000
        """
    )
    parser.add_argument("--host", type=str, default="0.0.0.0", 
                        help="UDP host to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=10002,
                        help="UDP port to listen on (default: 10002)")
    parser.add_argument("--urdf", type=str, default=None,
                        help="Path to URDF file (default: use built-in kbot)")
    
    args = parser.parse_args()
    
    # Get URDF path
    if args.urdf:
        urdf_path = args.urdf
    else:
        urdf_path = str(ASSETS_DIR / "kbot_legless" / "robot.urdf")
    
    print(f"\n🤖 Using URDF: {urdf_path}\n")
    
    # Create and run visualizer
    visualizer = RerunUDPVisualizer(urdf_path, host=args.host, port=args.port)
    visualizer.run()


if __name__ == "__main__":
    main()

