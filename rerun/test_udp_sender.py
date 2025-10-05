#!/usr/bin/env python3
"""
Test script to send robot joint positions to the rerun UDP visualizer.

Usage:
    python test_udp_sender.py [--host HOST] [--port PORT]
"""

import argparse
import json
import math
import socket
import time


def send_exact_udp_listener_message(host: str = "localhost", port: int = 10000, duration: float = 30.0):
    """
    Send the exact message from pyfirmware udp_listener.py over and over.
    
    Args:
        host: Target host
        port: Target UDP port
        duration: How long to run (seconds)
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    print(f"Sending exact udp_listener message to {host}:{port}")
    print(f"Press Ctrl+C to stop")
    
    # Exact message from pyfirmware/firmware/command_handling/udp_listener.py
    
    commands = [
        0.0,                    # XVel
        0.0,                    # YVel
        0.0,                    # YawRate
        0.0,                    # BaseHeight
        0.0,                    # BaseRoll
        0.0,                    # BasePitch
        0.0,                    # RShoulderPitch (21)
        math.radians(-10.0),    # RShoulderRoll (22)
        0.0,                    # RElbowPitch (24)
        math.radians(90.0),     # RElbowRoll (23)
        0.0,                    # RWristRoll (25)
        0.0,                    # LShoulderPitch (11)
        math.radians(10.0),     # LShoulderRoll (12)
        0.0,                    # LElbowPitch (14)
        math.radians(-90.0),    # LElbowRoll (13)
        0.0,                    # LWristRoll (15)
    ]
    
    start_time = time.time()
    frame = 0
    
    try:
        while time.time() - start_time < duration:
            message = {
                "commands": commands
            }
            
            # Send UDP packet
            sock.sendto(json.dumps(message).encode('utf-8'), (host, port))
            
            frame += 1
            if frame % 30 == 0:
                print(f"Sent {frame} frames ({frame / (time.time() - start_time):.1f} fps)")
            
            # Sleep to maintain ~30 fps
            time.sleep(1.0 / 30.0)
    
    except KeyboardInterrupt:
        print("\nStopped by user")
    finally:
        sock.close()
        print(f"Sent {frame} frames total")


def send_animated_positions(host: str = "localhost", port: int = 10000, duration: float = 30.0, use_array_format: bool = True):
    """
    Send animated robot joint positions over UDP.
    
    Args:
        host: Target host
        port: Target UDP port
        duration: How long to run the animation (seconds)
        use_array_format: If True, send as array [base(6), right(5), left(5)]. If False, use joint_angles dict.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    print(f"Sending animated joint positions to {host}:{port}")
    print(f"Press Ctrl+C to stop")
    
    # Actual joint names from the kbot URDF (from jax_ik.py active_joints)
    joint_names = [
        'dof_right_shoulder_pitch_03',
        'dof_right_shoulder_roll_03',
        'dof_right_shoulder_yaw_02',
        'dof_right_elbow_02',
        'dof_right_wrist_00',
        'dof_left_shoulder_pitch_03',
        'dof_left_shoulder_roll_03',
        'dof_left_shoulder_yaw_02',
        'dof_left_elbow_02',
        'dof_left_wrist_00'
    ]
    
    start_time = time.time()
    frame = 0
    
    try:
        while time.time() - start_time < duration:
            # Create sinusoidal motion for each joint
            t = time.time() - start_time
            
            # Right arm (5 joints) - EXTREMELY PRONOUNCED movement (radians)
            right_arm = [
                1.5 * math.sin(0.5 * t),           # shoulder yaw: ±1.5 rad (±86°)
                1.2 * math.sin(0.7 * t + 0.5),     # shoulder pitch: ±1.2 rad (±69°)
                1.0 * math.sin(0.6 * t + 1.0),     # shoulder roll: ±1.0 rad (±57°)
                1.8 * math.sin(0.8 * t + 1.5),     # elbow pitch: ±1.8 rad (±103°)
                2.0 * math.sin(0.9 * t + 2.0),     # wrist roll: ±2.0 rad (±115°)
            ]
            right_gripper = 0.5 + 0.4 * math.sin(1.0 * t)
            
            # Left arm (5 joints) - EXTREMELY PRONOUNCED movement (radians)
            left_arm = [
                1.5 * math.sin(0.6 * t + 3.0),     # shoulder yaw: ±1.5 rad (±86°)
                1.2 * math.sin(0.8 * t + 3.5),     # shoulder pitch: ±1.2 rad (±69°)
                1.0 * math.sin(0.7 * t + 4.0),     # shoulder roll: ±1.0 rad (±57°)
                1.8 * math.sin(0.9 * t + 4.5),     # elbow pitch: ±1.8 rad (±103°)
                2.0 * math.sin(1.0 * t + 5.0),     # wrist roll: ±2.0 rad (±115°)
            ]
            left_gripper = 0.5 + 0.4 * math.sin(1.1 * t)
            
            # Create message in requested format
            if use_array_format:
                # Array format: [base(6), right_arm(5), left_arm(5)]
                # Indices 6-10: RShoulderPitch, RShoulderRoll, RElbowPitch, RElbowRoll, RWristRoll
                # Indices 11-15: LShoulderPitch, LShoulderRoll, LElbowPitch, LElbowRoll, LWristRoll
                commands = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # Base joints (indices 0-5)
                commands += right_arm  # Right arm (indices 6-10)
                commands += left_arm   # Left arm (indices 11-15)
                
                message = {
                    "timestamp": time.time(),
                    "commands": commands
                }
            else:
                # Dictionary format with joint names
                joint_angles = {}
                for i in range(5):
                    joint_angles[joint_names[i]] = right_arm[i]
                for i in range(5):
                    joint_angles[joint_names[i + 5]] = left_arm[i]
                
                message = {
                    "timestamp": time.time(),
                    "joint_angles": joint_angles
                }
            
            # Send UDP packet
            sock.sendto(json.dumps(message).encode('utf-8'), (host, port))
            
            frame += 1
            if frame % 30 == 0:
                print(f"Sent {frame} frames ({frame / (time.time() - start_time):.1f} fps)")
            
            # Sleep to maintain ~30 fps
            time.sleep(1.0 / 30.0)
    
    except KeyboardInterrupt:
        print("\nStopped by user")
    finally:
        sock.close()
        print(f"Sent {frame} frames total")


def send_joint_angles_format(host: str = "localhost", port: int = 10000):
    """
    Send a single message using the joint_angles format with correct URDF joint names.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Example joint angles dictionary using actual URDF joint names
    joint_angles = {
        "dof_right_shoulder_pitch_03": 0.5,
        "dof_right_shoulder_roll_03": 0.3,
        "dof_right_shoulder_yaw_02": 0.2,
        "dof_right_elbow_02": 1.0,
        "dof_right_wrist_00": 0.0,
        "dof_left_shoulder_pitch_03": 0.5,
        "dof_left_shoulder_roll_03": -0.3,
        "dof_left_shoulder_yaw_02": -0.2,
        "dof_left_elbow_02": 1.0,
        "dof_left_wrist_00": 0.0,
    }
    
    message = {
        "timestamp": time.time(),
        "joint_angles": joint_angles
    }
    
    sock.sendto(json.dumps(message).encode('utf-8'), (host, port))
    print(f"Sent joint angles message to {host}:{port}")
    sock.close()


def main():
    parser = argparse.ArgumentParser(description="Test UDP sender for rerun visualizer")
    parser.add_argument("--host", type=str, default="localhost", help="Target host (default: localhost)")
    parser.add_argument("--port", type=int, default=10000, help="Target UDP port (default: 10000)")
    parser.add_argument("--mode", type=str, choices=["animate", "single", "exact"], default="exact",
                        help="Mode: 'animate' for continuous animation, 'single' for one message, 'exact' for udp_listener message")
    parser.add_argument("--duration", type=float, default=30.0, help="Animation duration in seconds (default: 30)")
    parser.add_argument("--format", type=str, choices=["array", "dict"], default="array",
                        help="Message format: 'array' for [base(6), right(5), left(5)], 'dict' for joint_angles dictionary")
    
    args = parser.parse_args()
    
    use_array = (args.format == "array")
    
    if args.mode == "exact":
        send_exact_udp_listener_message(args.host, args.port, args.duration)
    elif args.mode == "animate":
        send_animated_positions(args.host, args.port, args.duration, use_array_format=use_array)
    else:
        send_joint_angles_format(args.host, args.port)


if __name__ == "__main__":
    main()

