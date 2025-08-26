import numpy as np
import pandas as pd
from pathlib import Path
from scipy.spatial import ConvexHull
# This file is responsible for computing the transform between the task space of your arm and the kbot arm


hull_data = pd.read_csv(Path(__file__).absolute().parent / "kbot_arm_convex_hull.csv")
def fit_sphere_ransac(points, n_iters=2000, thresh=0.03, min_inliers=30, random_state=0):
    """Fit a sphere to 3D points using a simple RANSAC routine.
    WARNING: this is entire vibe-coded. Although, it seems to work.

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

center_k, radius_k, inliers_k = fit_sphere_ransac(hull_data.values, n_iters=2000, thresh=0.03, min_inliers=50)

def compute_transform(hand_positions: np.ndarray):
    hand_points_hull = ConvexHull(hand_positions)
    hull_pts = hand_positions[hand_points_hull.vertices]

    sphere_fit = fit_sphere_ransac(hull_pts, n_iters=2000, thresh=0.03, min_inliers=50)

    mat1 = np.eye(4)
    mat1[:3,3] = -sphere_fit[0]
    mat2 = np.eye(4)
    mat2[:3,:3] *= radius_k / sphere_fit[1]
    mat3 = np.eye(4)
    mat3[:3,3] = center_k

    # order of ops(right to left) is 1. center points around hand sphere fit. 2. scale to match kbot sphere 3. translate to kbot sphere center
    transform = mat3 @ mat2 @ mat1
    return transform
