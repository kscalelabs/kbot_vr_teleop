#!/usr/bin/env python3
"""Load newline-delimited JSON (ndjson) robot logs and replay to Rerun.

This mirrors the structure in `from_rerun_data.py` but without any hand
tracking. It visualizes the robot body from a URDF and logs time-series for
commands and other numeric arrays present in each record.

Usage:
  python from_ndjson.py /path/to/data.ndjson [--urdf /path/to/robot.urdf]

The input format expects one JSON object per line. Example fields supported:
- "joint_angles": list of joint positions (order matches URDF joints)
- "command": list/array (will be logged as time-series)
- "output", "joint_torques", "joint_vels", "joint_amps", etc.
"""

import argparse
import json
from pathlib import Path
import numpy as np
from tqdm import tqdm

import rerun as rr

from kscale_vr_teleop.analysis.rerun_loader_urdf import URDFLogger
from kscale_vr_teleop._assets import ASSETS_DIR
import warnings


def _log_numeric_array(name: str, arr):
    """Convenience: log lists/arrays of numbers as rr.Scalars."""
    try:
        a = np.asarray(arr, dtype=float)
    except Exception:
        return
    # For vectors we log the whole vector as Scalars (Rerun will show it as a
    # time-series / multi-scalar). For single-value arrays this still works.
    rr.log(name, rr.Scalars(a))


def main():
    parser = argparse.ArgumentParser(description="Replay ndjson robot logs to Rerun")
    parser.add_argument("filepath", type=str, help="Path to ndjson file (one JSON object per line)")
    parser.add_argument("--urdf", type=str, default=str(ASSETS_DIR / "kbot_legless" / "robot.urdf"), help="Path to URDF file to visualize")
    parser.add_argument("--recording-id", type=str, default=None)
    args = parser.parse_args()

    rr.init("replay_from_ndjson", recording_id=args.recording_id, spawn=True)
    rr.stdout()

    urdf_logger = URDFLogger(args.urdf)

    p = Path(args.filepath)
    if not p.exists():
        raise SystemExit(f"ndjson file not found: {p}")

    # We log each record in sequence. The URDFLogger accepts a list/tuple of
    # joint angles (in the order of the URDF joints) or a dict mapping joint
    # name -> angle.
    with p.open("r") as fh:
        for i, line in enumerate(tqdm(fh, desc="records")):
            line = line.strip()
            if not line:
                warnings.warn(f"Skipping malformed line {i}")
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                # skip malformed lines
                warnings.warn(f"Skipping malformed JSON line {i}")
                continue

            # timestamps are in microseconds; convert to seconds and set Rerun time
            t_raw = rec.get("t_us")
            rr.set_time("my_timeline", timestamp=t_raw/1e6)

            # joint angles -> robot pose
            joints = rec.get("joint_angles")

            

    print("Done")


if __name__ == "__main__":
    main()

import json

# ex: {"step_id":0,"t_us":1757119114254905,"joint_angles":[0.0,-0.017832799,0.0,0.016298795,0.0,0.15819418,0.0,-0.1616457,0.0,-0.011313281,0.0,0.006807144,0.0,-1.5440711,0.0,1.5433999,0.0,0.0041226363,0.0,0.0013422536,0.0,0.0],"joint_vels":[0.0,-0.00045014115,0.0,-0.0018081941,0.0,0.00095368887,0.0,0.00046540017,0.0,0.00051117723,0.0,-0.0006942855,0.0,-0.00058747234,0.0,0.001029984,0.0,0.0000686656,0.0,0.00009918364,0.0,0.0],"initial_heading":null,"joint_amps":[0.0,1.2099434,0.0,-1.1106651,0.0,1.0329652,0.0,-0.8911132,0.0,0.4509333,0.0,-0.36497325,0.0,-2.3643105,0.0,2.3368125,0.0,-0.13539478,0.0,-0.041209284,0.0,0.0],"joint_torques":[0.0,1.7019913,0.0,-1.672694,0.0,1.518883,0.0,-1.3339437,0.0,0.45525292,0.0,-0.3084306,0.0,-2.1424124,0.0,2.1159532,0.0,-0.14334325,0.0,-0.03695735,0.0,0.0],"joint_temps":[0.0,28.0,0.0,28.0,0.0,28.0,0.0,28.0,0.0,28.0,0.0,28.0,0.0,29.0,0.0,29.0,0.0,30.0,0.0,30.0,0.0,0.0],"quaternion":null,"projected_g":[-0.27429265,-9.772009,-0.81774616],"accel":null,"gyro":[0.0010652645,0.0,0.0],"command":[0.0,0.0,0.0,0.0,0.0,0.0,-0.2617994,0.0,1.5707964,0.0,0.0,0.0,0.2617994,0.0,-1.5707964,0.0,0.0,0.0],"output":[0.0,0.0,0.0,-0.2617994,0.0,-1.5707964,0.0,0.0,0.0,0.0,0.0,1.5707964,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.2617994]}
