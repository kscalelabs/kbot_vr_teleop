import rerun as rr
import polars as pl
import numpy as np
from pathlib import Path
from transforms.compute_transforms import compute_transform
from arm_inverse_kinematics import new_calculate_arm_joints, calculate_arm_joints, arms_robot, right_chain, jax_calculate_arm_joints, right_arm_links
from analysis.rerun_loader_urdf import URDFLogger
from tqdm import tqdm
from line_profiler import profile

urdf_logger = URDFLogger("/home/miller/code/vr_teleop/src/assets/kbot/robot.urdf")

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

# Load recording and convert to a Polars dataframe
recording_path = Path(__file__).parent / "vr_teleop_irl_data.rrd"
recording = rr.dataframe.load_recording(str(recording_path))
view = recording.view(index="log_time", contents="/**")
df = pl.from_arrow(view.select().read_all())

# filter coumns where '/right_wrist:Translation3D is not None
df = df.filter(pl.col('/right_wrist:Translation3D').is_not_null())

# Build numpy array of translations for computing the transform
translations = np.vstack([
	np.asarray(x).reshape(3,) for x in df['/right_wrist:Translation3D'].to_list()
])

# Compute transform mapping recorded hand poses into kbot space
# transform = compute_transform(translations)
transform = np.eye(4)
transform[:3,3] = np.array([
	0, 0, 0.25
])

# Visualize the task-space sphere (static)
# task_space_sphere = sphere_points(center_k, radius_k, n_theta=48, n_phi=24)
# rr.log('task_space_sphere', rr.Points3D(task_space_sphere, colors=[[0,255,255]]*len(task_space_sphere), radii=[0.001]*len(task_space_sphere)), static=True)
# draw axes on origin
rr.log('origin_axes', rr.Transform3D(translation=[0,0,0], axis_length=0.1), static=True)

# initialize robot config
arms_robot.update_cfg({k.name: 0 for k in arms_robot.actuated_joints})


# Iterate frames and perform IK + visualization
err = []
@profile
def main():
    for i, row in enumerate(tqdm(df.iter_rows(named=True), total=len(df))):
        # read translation and rotation (user confirmed these parse correctly)
        translation = np.array(row['/right_wrist:Translation3D']).reshape(3,)
        rot_cell = row.get('/right_wrist:TransformMat3x3')
        if rot_cell is None:
            rotation = np.eye(3)
        else:
            rotation = np.array(rot_cell).reshape((3,3))

        frame_mat = np.eye(4)
        frame_mat[:3,:3] = rotation
        frame_mat[:3,3] = translation

        # map to kbot space
        frame_mat = transform @ frame_mat

        # timestamp if present
        timestamp = row.get('log_time') if 'log_time' in row else None
        if timestamp is None:
            timestamp = int(i)

        # IK computations
        _, old_arm_joint_angles = calculate_arm_joints(np.eye(4), np.eye(4), frame_mat)
        _, arm_joint_angles = new_calculate_arm_joints(np.eye(4), np.eye(4), frame_mat)

        rr.set_time_seconds('my_timeline', timestamp.timestamp())

        # forward kinematics positions
        fk_wrist_position = right_chain.forward_kinematics(arm_joint_angles)[:3,3]

        # apply old solution to robot config (old_arm_joint_angles already sampled in calculate_arm_joints)
        new_config = {k.name: old_arm_joint_angles[i] for i, k in enumerate(arms_robot.actuated_joints[::2])}
        arms_robot.update_cfg(new_config)
        old_fk_wrist_position = arms_robot.get_transform('KB_C_501X_Right_Bayonet_Adapter_Hard_Stop', 'base')[:3,3]

        # _, jax_joints = jax_calculate_arm_joints(np.eye(4), np.eye(4), frame_mat)

        # new_config = {k.name: jax_joints[i] for i, k in enumerate(arms_robot.actuated_joints[::2])}
        # arms_robot.update_cfg(new_config)
        # jax_ee_position = arms_robot.get_transform('KB_C_501X_Right_Bayonet_Adapter_Hard_Stop', 'base')[:3,3]

        # compute L2 residuals (target position vs each solver's end-effector position)
        target_pos = frame_mat[:3,3]
        res_new = float(np.linalg.norm(fk_wrist_position - target_pos))
        res_old = float(np.linalg.norm(old_fk_wrist_position - target_pos))
        # res_jax = float(np.linalg.norm(jax_ee_position - target_pos))

        # log residuals as scalars so Rerun can plot them over time
        rr.log('residual_new', rr.Scalar(res_new))
        rr.log('residual_old', rr.Scalar(res_old))
        err.append(res_old)
        # rr.log('residual_jax', rr.Scalar(res_jax))

        # Rerun logging
        rr.log('fk_position', rr.Points3D([fk_wrist_position], colors=[[255,0,0]], radii=0.01))
        # rr.log('jax_ee_position', rr.Points3D([jax_ee_position], colors=[[255,0,255]], radii=0.01))
        rr.log('old_fk_position', rr.Points3D([old_fk_wrist_position], colors=[[0,0,255]], radii=0.01))
        rr.log('target_position', rr.Transform3D(translation=frame_mat[:3,3], mat3x3=frame_mat[:3,:3], axis_length=0.05))

        # new_config = {k.name: old_arm_joint_angles[i] for i, k in enumerate(arms_robot.actuated_joints[::2])}
        # print([k.name for k in arms_robot.actuated_joints[::2]])
        # arms_robot.update_cfg(new_config)
        # positions = [arms_robot.get_transform(link, 'base')[:3,3] for link in right_arm_links]
        # rr.log('kinematic_chain', rr.LineStrips3D(positions, colors=[[255,255,255]]*(len(positions)-1), radii=0.005))
        urdf_logger.log()

    print('Done')
    mse = np.mean(np.array(err)**2)
    print(f'MSE: {mse}')
    rr.log('mse', rr.Scalar(mse), static=True)

main()