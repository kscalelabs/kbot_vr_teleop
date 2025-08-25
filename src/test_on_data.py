
import pandas as pd
import numpy as np
from arm_inverse_kinematics import new_calculate_arm_joints, calculate_arm_joints, arms_robot, right_chain
from scipy.spatial.transform import Rotation
from pathlib import Path
import rerun as rr

rr.init("scrub_ik_data", spawn=True)

#example
# timestamp,x,y,z,qx,qy,qz,qw
# 1756145288.7937613,0.37432602047920227,-0.18940892815589905,1.4978502988815308,0.8042818510899596,-0.46995448460681816,-0.3010130247599319,0.20411919392875483



raw_data = pd.read_csv(Path(__file__).absolute().parent / "right_wrist_data.csv")
# rr.send_columns('wrist_pose', indexes = [rr.TimeSecondsColumn('my_timeline', raw_data['timestamp'].values)], columns = [*rr.Points3D.columns(positions=raw_data[['x', 'y', 'z']].values)])

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
    fk_wrist_position = right_chain.forward_kinematics([0,*arm_joint_angles,0])[:3,3]
    new_config={
        k.name: old_arm_joint_angles[i] for i, k in enumerate(arms_robot.actuated_joints[::2])
    }
    arms_robot.update_cfg(new_config)
    old_fk_wrist_position = arms_robot.get_transform('KB_C_501X_Right_Bayonet_Adapter_Hard_Stop', 'base')[:3,3]
    # fk_wrist_position -= np.array([0,0,-1.5])
    # old_fk_wrist_position -= np.array([0,0,-1.5])
    rr.log('fk_position', rr.Points3D([fk_wrist_position]))
    rr.log('old_fk_position', rr.Points3D([old_fk_wrist_position]))
    rr.log('target_position', rr.Points3D([frame_mat[:3,3]]))


print("Done")