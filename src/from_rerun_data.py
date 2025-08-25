import rerun as rr
import polars as pl
import numpy as np
from pathlib import Path
from transforms.compute_transforms import compute_transform, center_k, radius_k
from arm_inverse_kinematics import new_calculate_arm_joints, calculate_arm_joints, arms_robot, right_chain, placo_calculate_arm_joints, placo_robot
from tqdm import tqdm


def sphere_points(center, radius, n_theta=32, n_phi=16):
	"""Generate points on sphere surface for visualization."""
	theta = np.linspace(0, 2 * np.pi, n_theta, endpoint=False)
	phi = np.linspace(0, np.pi, n_phi)
	tt, pp = np.meshgrid(theta, phi)
	x = np.sin(pp) * np.cos(tt)
	y = np.sin(pp) * np.sin(tt)
	z = np.cos(pp)
	pts = np.stack((x.flatten(), y.flatten(), z.flatten()), axis=-1) * radius + center
	return pts


rr.init("scrub_ik_data_from_rerun", spawn=True)

# Load recording and convert to a Polars dataframe
recording_path = Path(__file__).parent / "wrist_translated_to_head.rrd"
recording = rr.dataframe.load_recording(str(recording_path))
view = recording.view(index="log_time", contents="/**")
df = pl.from_arrow(view.select().read_all())

# filter coumns where '/right_wrist:Translation3D is not None
df = df.filter(pl.col('/right_wrist:Translation3D').is_not_null())

print(df)

for row in df.iter_rows(named=True):
    translation = np.array(row['/right_wrist:Translation3D'])
    rotation = np.array(row['/right_wrist:TransformMat3x3']).reshape((3,3))
    frame_mat = np.eye(4)
    frame_mat[:3,:3] = rotation
    frame_mat[:3,3] = translation

    print(frame_mat)