import rerun as rr
import polars as pl
import numpy as np
from pathlib import Path
from kscale_vr_teleop.analysis.rerun_loader_urdf import URDFLogger
from tqdm import tqdm
from line_profiler import profile
from kscale_vr_teleop.udp_conn import UDPHandler, RLUDPHandler
from kscale_vr_teleop.jax_ik import RobotInverseKinematics
from kscale_vr_teleop._assets import ASSETS_DIR

urdf_path  = str(ASSETS_DIR / "kbot_legless" / "robot.urdf")
urdf_logger = URDFLogger(urdf_path)


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


rr.init("replay_teleop_from_rerun", spawn=True)

recording_path = "/home/miller/.vr_teleop_logs/2025-09-05/11-11-34.rrd"
recording = rr.dataframe.load_recording(str(recording_path))
view = recording.view(index="log_time", contents="/**")
df = pl.from_arrow(view.select().read_all())

# df = df.filter(pl.col('/right_wrist:Transform3D:translation').is_not_null() and pl.col('/left_wrist:Transform3D:translation').is_not_null())

# translations = np.vstack([
# 	np.asarray(x).reshape(3,) for x in df['/right_wrist:Transform3D:translation'].to_list()
# ])

base_to_head_transform = np.eye(4)
# base_to_head_transform[:3,3] = np.array([
# 	0, 0, 0.25
# ])

rr.log('origin_axes', rr.Transform3D(translation=[0,0,0], axis_length=0.1), static=True)


udp_handler = UDPHandler("127.0.0.1", 8888)

ik_solver = RobotInverseKinematics(urdf_path, ['PRT0001', 'PRT0001_2'], 'base')

err = []
@profile
def main():
    left_wrist_frame = np.eye(4)
    right_wrist_frame = np.eye(4)
    for i, row in enumerate(tqdm(df.iter_rows(named=True), total=len(df))):
        right_translate = row['/right_wrist:Transform3D:translation']
        right_rot = row.get('/right_wrist:Transform3D:mat3x3')
        left_translate = row['/left_wrist:Transform3D:translation']
        left_rot = row.get('/left_wrist:Transform3D:mat3x3')

        # right_wrist_frame = np.eye(4)
        if right_rot is not None:
            right_wrist_frame[:3,:3] = np.array(right_rot).reshape((3,3))
            right_wrist_frame[:3,3] = np.array(right_translate).reshape(3,)
        # left_wrist_frame = np.eye(4)
        if left_rot is not None:
            left_wrist_frame[:3,:3] = np.array(left_rot).reshape((3,3))
            left_wrist_frame[:3,3] = np.array(left_translate).reshape(3,)

        right_wrist_frame = base_to_head_transform @ right_wrist_frame
        left_wrist_frame = base_to_head_transform @ left_wrist_frame

        timestamp = row.get('log_time') if 'log_time' in row else None
        if timestamp is None:
            timestamp = int(i)

        # left_arm_joints, right_arm_joints = calculate_arm_joints(np.eye(4), np.eye(4), frame_mat)
        joints = ik_solver.inverse_kinematics(np.array([right_wrist_frame, left_wrist_frame]))
        left_arm_joints = joints[1::2]
        right_arm_joints = joints[::2]

        new_config = {k.name: right_arm_joints[i] for i, k in enumerate(ik_solver.active_joints[::2])}
        new_config.update({k.name: left_arm_joints[i] for i, k in enumerate(ik_solver.active_joints[1::2])})

        rr.log('target_right', rr.Transform3D(translation=right_wrist_frame[:3,3], mat3x3=right_wrist_frame[:3,:3], axis_length=0.05))
        rr.log('target_left', rr.Transform3D(translation=left_wrist_frame[:3,3], mat3x3=left_wrist_frame[:3,:3], axis_length=0.05))

        urdf_logger.log(new_config)

        udp_handler._send_udp(right_arm_joints, left_arm_joints, np.zeros(6), np.zeros(6))

    print('Done')
    mse = np.mean(np.array(err)**2)
    print(f'MSE: {mse}')
    rr.log('mse', rr.Scalars(mse), static=True)

main()
