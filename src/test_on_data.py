
import pandas as pd
import numpy as np
from arm_inverse_kinematics import new_calculate_arm_joints, calculate_arm_joints, arms_robot, right_chain, placo_calculate_arm_joints, placo_robot
from scipy.spatial.transform import Rotation
from pathlib import Path
import rerun as rr

rr.init("scrub_ik_data", spawn=True)

#example
# timestamp,x,y,z,qx,qy,qz,qw
# 1756145288.7937613,0.37432602047920227,-0.18940892815589905,1.4978502988815308,0.8042818510899596,-0.46995448460681816,-0.3010130247599319,0.20411919392875483



raw_data = pd.read_csv(Path(__file__).absolute().parent / "right_wrist_data.csv")
hull_data = pd.read_csv(Path(__file__).absolute().parent / "kbot_arm_convex_hull.csv")
rr.log('task_space_hull', rr.Points3D(hull_data.values, colors=[[0,200,200]]*len(hull_data)), static=True)
def fit_sphere_ransac(points, n_iters=2000, thresh=0.03, min_inliers=30, random_state=0):
    """Fit a sphere to 3D points using a simple RANSAC routine.

    Returns (center, radius, inlier_mask).
    """
    rng = np.random.RandomState(random_state)
    best = {'inliers': None, 'count': 0, 'center': None, 'radius': None}
    pts = np.asarray(points, dtype=float)
    N = pts.shape[0]
    if N < 4:
        raise ValueError('Need at least 4 points to fit a sphere')

    for _ in range(n_iters):
        # sample 4 points
        idx = rng.choice(N, 4, replace=False)
        psel = pts[idx]
        # build linear system: A * [a,b,c,d] = bvec where
        # x^2+y^2+z^2 + a x + b y + c z + d = 0
        A = np.column_stack((psel[:, 0], psel[:, 1], psel[:, 2], np.ones(4)))
        bvec = -(psel[:, 0] ** 2 + psel[:, 1] ** 2 + psel[:, 2] ** 2)
        try:
            sol, *_ = np.linalg.lstsq(A, bvec, rcond=None)
        except np.linalg.LinAlgError:
            continue
        a, b, c, d = sol
        center = -0.5 * np.array([a, b, c])
        rad2 = center.dot(center) - d
        if rad2 <= 0 or not np.isfinite(rad2):
            continue
        radius = np.sqrt(rad2)

        # compute residuals
        dists = np.linalg.norm(pts - center[None, :], axis=1)
        residuals = np.abs(dists - radius)
        inliers = residuals <= thresh
        count = int(inliers.sum())
        if count > best['count'] and count >= min_inliers:
            best.update({'inliers': inliers, 'count': count, 'center': center, 'radius': radius})

    # If no good model found, refit on all points using least squares
    if best['center'] is None:
        # fallback: fit to all points
        A = np.column_stack((pts[:, 0], pts[:, 1], pts[:, 2], np.ones(N)))
        bvec = -(pts[:, 0] ** 2 + pts[:, 1] ** 2 + pts[:, 2] ** 2)
        sol, *_ = np.linalg.lstsq(A, bvec, rcond=None)
        a, b, c, d = sol
        center = -0.5 * np.array([a, b, c])
        rad2 = center.dot(center) - d
        radius = np.sqrt(rad2) if rad2 > 0 else 0.0
        inliers = np.abs(np.linalg.norm(pts - center[None, :], axis=1) - radius) <= thresh
        return center, radius, inliers

    # optional refine fit on inliers
    inlier_pts = pts[best['inliers']]
    A = np.column_stack((inlier_pts[:, 0], inlier_pts[:, 1], inlier_pts[:, 2], np.ones(inlier_pts.shape[0])))
    bvec = -(inlier_pts[:, 0] ** 2 + inlier_pts[:, 1] ** 2 + inlier_pts[:, 2] ** 2)
    sol, *_ = np.linalg.lstsq(A, bvec, rcond=None)
    a, b, c, d = sol
    center = -0.5 * np.array([a, b, c])
    rad2 = center.dot(center) - d
    radius = np.sqrt(rad2) if rad2 > 0 else 0.0
    inliers = np.abs(np.linalg.norm(pts - center[None, :], axis=1) - radius) <= thresh
    return center, radius, inliers


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


# Fit and display a sphere for the robot hull
try:
    center_k, radius_k, inliers_k = fit_sphere_ransac(hull_data.values, n_iters=2000, thresh=0.03, min_inliers=20)
    print(f"Fitted kbot sphere: center={center_k}, radius={radius_k}")
    sph_pts = sphere_points(center_k, radius_k, n_theta=48, n_phi=24)
    rr.log('task_space_sphere', rr.Points3D(sph_pts, colors=[[0,255,255]]*len(sph_pts)), static=True)
    # show inlier points on the hull
    try:
        rr.log('task_space_sphere_inliers', rr.Points3D(hull_data.values[inliers_k], colors=[[0,100,100]]*int(inliers_k.sum())), static=True)
    except Exception:
        pass
except Exception as e:
    print('Could not fit kbot sphere:', e)


human_hull_data = pd.read_csv(Path(__file__).absolute().parent / "human_arm_convex_hull.csv")
rr.log('human_task_space_hull', rr.Points3D(human_hull_data.values, colors=[[200,0,200]]*len(human_hull_data)), static=True)
try:
    center_h, radius_h, inliers_h = fit_sphere_ransac(human_hull_data.values, n_iters=2000, thresh=0.03, min_inliers=20)
    print(f"Fitted human sphere: center={center_h}, radius={radius_h}")
    sph_pts_h = sphere_points(center_h, radius_h, n_theta=48, n_phi=24)
    rr.log('human_task_space_sphere', rr.Points3D(sph_pts_h, colors=[[255,0,255]]*len(sph_pts_h)), static=True)
    try:
        rr.log('human_task_space_sphere_inliers', rr.Points3D(human_hull_data.values[inliers_h], colors=[[100,0,100]]*int(inliers_h.sum())), static=True)
    except Exception:
        pass
except Exception as e:
    print('Could not fit human sphere:', e)




# rr.send_columns('wrist_pose', indexes = [rr.TimeSecondsColumn('my_timeline', raw_data['timestamp'].values)], columns = [*rr.Points3D.columns(positions=raw_data[['x', 'y', 'z']].values)])

arms_robot.update_cfg({
    k.name: 0 for k in arms_robot.actuated_joints
})

at_rest_position = arms_robot.get_transform('KB_C_501X_Right_Bayonet_Adapter_Hard_Stop', 'base')[:3,3]

at_rest_ikpy_position = right_chain.forward_kinematics([0]*7)[:3,3]

print(at_rest_position, at_rest_ikpy_position)

for i, row in raw_data.iterrows():
    # Compose wrist pose matrix
    timestamp = row[0]
    frame_mat = np.eye(4)
    frame_mat[:3, 3] = row[1:4].values
    frame_mat[:3, :3] = Rotation.from_quat(row[4:]).as_matrix()

    frame_mat[:3, 3] += np.array([0,0,-1.5]) # move down to roughly match urdf coordinate system

    # Calculate joint angles
    _,old_arm_joint_angles = calculate_arm_joints(np.eye(4), np.eye(4), frame_mat)
    _, arm_joint_angles = new_calculate_arm_joints(np.eye(4), np.eye(4), frame_mat)
    rr.set_time_seconds('my_timeline', timestamp)
    # rr.log('shoulder_pitch', rr.Scalar(arm_joint_angles[0]))
    # rr.log('shoulder_roll', rr.Scalar(arm_joint_angles[1]))
    # rr.log('shoulder_yaw', rr.Scalar(arm_joint_angles[2]))
    # rr.log('elbow', rr.Scalar(arm_joint_angles[3]))
    # rr.log('wrist', rr.Scalar(arm_joint_angles[4]))
    # Log wrist pose as a point (use time argument)
    fk_wrist_position = right_chain.forward_kinematics(arm_joint_angles)[:3,3]
    new_config={
        k.name: old_arm_joint_angles[i] for i, k in enumerate(arms_robot.actuated_joints[::2])
    }
    arms_robot.update_cfg(new_config)
    old_fk_wrist_position = arms_robot.get_transform('KB_C_501X_Right_Bayonet_Adapter_Hard_Stop', 'base')[:3,3]

    _, placo_joints = placo_calculate_arm_joints(np.eye(4), np.eye(4), frame_mat)
    placo_ee_position = placo_robot.forward_kinematics(placo_joints)[:3,3]

    # old_fk_wrist_position = right_chain.forward_kinematics([0,*old_arm_joint_angles,0])[:3,3]
    # fk_wrist_position -= np.array([0,0,-1.5])
    # old_fk_wrist_position -= np.array([0,0,-1.5])
    rr.log('fk_position', rr.Points3D([fk_wrist_position], colors=[[255,0,0]]))
    rr.log('old_fk_position', rr.Points3D([old_fk_wrist_position], colors=[[0,0,255]]))
    rr.log('placo_ee_position', rr.Points3D([placo_ee_position], colors=[[255,255,0]]))
    rr.log('target_position', rr.Points3D([frame_mat[:3,3]], colors=[[0,255,0]]))


print("Done")