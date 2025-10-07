#!/usr/bin/env python3
"""
Simple test script to send robot commands with joint biases.
"""

import argparse
import json
import math
import socket
import time


def main():
    parser = argparse.ArgumentParser(description="Test UDP sender with joint biases")
    parser.add_argument("--host", type=str, default="localhost", help="Target host")
    parser.add_argument("--port", type=int, default=10000, help="Target UDP port")
    parser.add_argument("--duration", type=float, default=30.0, help="Duration in seconds")
    
    args = parser.parse_args()
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    print(f"Sending commands to {args.host}:{args.port}")
    print(f"Press Ctrl+C to stop")
    
    # Start with joint biases (from command_conn.py add_joint_bias)
    start_commands = {
        "xvel": 0.0,
        "yvel": 0.0,
        "yawrate": 0.0,
        "baseheight": 0.0,
        "baseroll": 0.0,
        "basepitch": 0.0,
        "rshoulderpitch": 0.0,
        "rshoulderroll": math.radians(-10.0),     # +10°
        "rshoulderyaw": 0.0,
        "relbowpitch": math.radians(90.0),      # -90°
        "rwristroll": 0.0,
        "rwristgripper": math.radians(-8.0),     # -8°
        "lshoulderpitch": 0.0,
        "lshoulderroll": math.radians(10.0),    # -10°
        "lshoulderyaw": 0.0,
        "lelbowpitch": math.radians(-90.0),       # +90°
        "lwristroll": 0.0,
        "lwristgripper": math.radians(-25.0),    # -25°
    }
    
    # Oscillate ±10° for all actuators
    oscillation_amplitude = math.radians(10.0)
    
    start_time = time.time()
    frame = 0
    
    try:
        while time.time() - start_time < args.duration:
            # Calculate oscillation based on time
            t = time.time() - start_time
            oscillation = oscillation_amplitude * math.sin(0.5 * t)  # ±10° oscillation
            
            # Apply oscillation to all actuators
            commands = start_commands.copy()
            for key in commands:
                if key.startswith(('r', 'l')) and ('shoulder' in key or 'elbow' in key or 'wrist' in key):
                    commands[key] += oscillation
            
            message = {"commands": commands}
            
            # Send UDP packet
            sock.sendto(json.dumps(message).encode('utf-8'), (args.host, args.port))
            
            frame += 1
            if frame % 30 == 0:
                print(f"Frame {frame}, oscillation: {math.degrees(oscillation):.1f}°")
            
            time.sleep(1.0 / 30.0)  # 30 fps
    
    except KeyboardInterrupt:
        print("\nStopped by user")
    finally:
        sock.close()
        print(f"Sent {frame} frames total")


if __name__ == "__main__":
    main()

