"""Compute the kbot right-arm working envelope by random sampling.

This script samples joint angles uniformly within joint limits, computes the
end-effector position for each sample, computes the convex hull of the sampled
end-effector points, and writes the hull vertices to a CSV file (one point per row).

Notes:
- Default is 10_000_000 samples. This can be changed with the --samples flag.
- Sampling is performed in chunks to limit memory usage and can be parallelized.
- Running 10M forward-kinematics calls may take a long time; this script is
  intentionally chunked and parallel-friendly.
"""

from pathlib import Path
import argparse
import multiprocessing as mp
import numpy as np
from functools import partial

try:
    from scipy.spatial import ConvexHull
except Exception:
    ConvexHull = None


def get_joint_limits(urdf_path: Path, joint_names):
    """Return list of (lower, upper) limits (degrees) for joint_names.

    Falls back to [-180, 180] degrees if a joint limit is not present in the URDF.
    """
    try:
        from yourdfpy import URDF
    except Exception as e:
        raise ImportError("yourdfpy is required to read joint limits from URDF") from e

    urdf = URDF.load(str(urdf_path), build_scene_graph=False)
    limits_map = {j.name: (j.limit.lower, j.limit.upper) for j in urdf.actuated_joints}

    limits = []
    for name in joint_names:
        if name in limits_map:
            lb, ub = limits_map[name]
            # URDF limits are typically in radians; try to detect and convert if needed
            # Heuristic: if bounds are within [-2pi, 2pi] assume radians and convert to degrees
            if abs(lb) <= 2 * np.pi and abs(ub) <= 2 * np.pi:
                lb_deg = np.degrees(lb)
                ub_deg = np.degrees(ub)
            else:
                lb_deg = lb
                ub_deg = ub
            limits.append((lb_deg, ub_deg))
        else:
            # reasonable fallback
            limits.append((-180.0, 180.0))
    return limits


def worker_sample(args):
    """Worker that samples joint space and returns EE positions array (N x 3).

    This function recreates a RobotKinematics instance in the worker process to
    avoid pickling issues with placo/RobotWrapper.
    """
    urdf_path, target_frame_name, joint_names, limits, n_samples, seed = args

    # Import here (inside worker)
    from lerobot.model.kinematics import RobotKinematics

    rng = np.random.RandomState(seed)
    rk = RobotKinematics(str(urdf_path), target_frame_name, joint_names)

    lower = np.array([l for l, _ in limits], dtype=float)
    upper = np.array([u for _, u in limits], dtype=float)
    n_j = len(joint_names)

    out = np.empty((n_samples, 3), dtype=np.float64)
    for i in range(n_samples):
        joints = rng.uniform(lower, upper)
        # RobotKinematics.forward_kinematics expects degrees and returns a 4x4 transform
        T = rk.forward_kinematics(joints)
        out[i, :] = T[:3, 3]
        if (i + 1) % 20000 == 0:
            # lightweight progress hint in worker
            print(f"pid={mp.current_process().pid} sampled {i+1}/{n_samples}")
    return out


def main():
    parser = argparse.ArgumentParser(description="Compute kbot arm working envelope via random sampling")
    parser.add_argument("--samples", type=int, default=10_000_000, help="Total number of random samples (default 10_000_000)")
    parser.add_argument("--chunk-size", type=int, default=100_000, help="Samples per chunk processed by a worker (default 100_000)")
    parser.add_argument("--processes", type=int, default=max(1, mp.cpu_count() - 1), help="Number of parallel processes (default CPU-1)")
    parser.add_argument("--out", type=Path, default=Path("kbot_arm_convex_hull.csv"), help="Output CSV file for convex hull points")
    parser.add_argument("--urdf", type=Path, default=Path(__file__).parent / "assets" / "kbot" / "robot.urdf", help="Path to kbot URDF (defaults to repo assets)")
    parser.add_argument("--target-frame", type=str, default="KB_C_501X_Right_Bayonet_Adapter_Hard_Stop", help="End-effector frame name in URDF")
    args = parser.parse_args()

    if ConvexHull is None:
        raise RuntimeError("scipy.spatial.ConvexHull is required. Install scipy.")

    # Determine joint names to sample: use RobotKinematics to get the default joint set for the arm
    try:
        from lerobot.model.kinematics import RobotKinematics
    except Exception as e:
        raise ImportError("lerobot.model.kinematics.RobotKinematics must be importable (see kteelop dependency in workspace)") from e

    # Create a temporary instance to learn the joint names
    rk_tmp = RobotKinematics(str(args.urdf), args.target_frame)
    joint_names = rk_tmp.joint_names

    # Prefer sampling the right arm only when available (smaller, faster).
    preferred_right = [
        'dof_right_shoulder_pitch_03',
        'dof_right_shoulder_roll_03',
        'dof_right_shoulder_yaw_02',
        'dof_right_elbow_02',
        'dof_right_wrist_00'
    ]
    if all(name in joint_names for name in preferred_right):
        joint_names = preferred_right

    print(f"Sampling joints: {joint_names}")

    # Get joint limits (degrees)
    limits = get_joint_limits(args.urdf, joint_names)
    for name, (lo, hi) in zip(joint_names, limits):
        print(f"  {name}: [{lo:.2f}, {hi:.2f}] deg")

    total = args.samples
    chunk = args.chunk_size
    n_procs = max(1, args.processes)

    # Prepare worker args list
    chunks = []
    n_full = total // chunk
    rem = total % chunk
    seeds_base = np.random.SeedSequence(12345).spawn(n_full + (1 if rem else 0))

    for i in range(n_full):
        chunks.append((args.urdf, args.target_frame, joint_names, limits, chunk, seeds_base[i].entropy))
    if rem:
        chunks.append((args.urdf, args.target_frame, joint_names, limits, rem, seeds_base[-1].entropy))

    print(f"Total samples: {total}, chunks: {len(chunks)}, processes: {n_procs}")

    # Run workers in parallel
    all_points = []
    if n_procs == 1:
        for idx, c in enumerate(chunks):
            print(f"Processing chunk {idx+1}/{len(chunks)} (n={c[4]})")
            pts = worker_sample(c)
            all_points.append(pts)
    else:
        with mp.Pool(processes=n_procs) as pool:
            for idx, pts in enumerate(pool.imap_unordered(worker_sample, chunks)):
                print(f"Received chunk {idx+1}/{len(chunks)} -> {pts.shape[0]} points")
                all_points.append(pts)

    all_points = np.vstack(all_points)
    print(f"Collected {all_points.shape[0]} end-effector samples")

    if all_points.shape[0] < 4:
        raise RuntimeError("Not enough points for a 3D convex hull")

    print("Computing convex hull (this may take some time)")
    hull = ConvexHull(all_points)
    hull_points = all_points[hull.vertices]
    print(f"Convex hull has {hull_points.shape[0]} vertices")

    print(f"Saving hull points to {args.out}")
    np.savetxt(str(args.out), hull_points, delimiter=",")
    print("Done")


if __name__ == "__main__":
    main()
