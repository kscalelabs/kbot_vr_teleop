import rerun as rr
import polars as pl
import numpy as np
from pathlib import Path
from tqdm import tqdm
from line_profiler import profile
from kscale_vr_teleop.teleop_core import TeleopCore
import warnings

rr.init("replay_teleop_from_rerun", spawn=True)

recording_path = "/home/miller/Downloads/16-10-29.rrd"
recording = rr.dataframe.load_recording(str(recording_path))
view = recording.view(index="log_time", contents="/**")
df = pl.from_arrow(view.select().read_all())

teleop_core = TeleopCore()
teleop_core.update_head(np.eye(4))

rr.log('origin_axes', rr.Transform3D(translation=[0,0,0], axis_length=0.1), static=True)

err = []
@profile
def main():
    left_wrist_frame = np.eye(4)
    right_wrist_frame = np.eye(4)
    for i, row in enumerate(tqdm(df.iter_rows(named=True), total=len(df))):
        timestamp = row.get('log_time') if 'log_time' in row else None
        if timestamp is None:
            warnings.warn(f"Skipping row {i} with missing log_time")
            timestamp = int(i)
        rr.set_time('', timestamp=timestamp)
        right_translate = row['/right_wrist:Transform3D:translation']
        right_rot = row.get('/right_wrist:Transform3D:mat3x3')
        left_translate = row['/left_wrist:Transform3D:translation']
        left_rot = row.get('/left_wrist:Transform3D:mat3x3')

        # right_wrist_frame = np.eye(4)
        if right_rot is not None:
            right_wrist_frame[:3,:3] = np.array(right_rot).reshape((3,3))
            right_wrist_frame[:3,3] = np.array(right_translate).reshape(3,)
            # rr.log('right_wrist', rr.Transform3D(translation=right_wrist_frame[:3, 3], mat3x3=right_wrist_frame[:3, :3], axis_length=0.05))
            teleop_core.update_right_hand(right_wrist_frame, np.zeros((24,4,4)))
        # left_wrist_frame = np.eye(4)
        if left_rot is not None:
            left_wrist_frame[:3,:3] = np.array(left_rot).reshape((3,3))
            left_wrist_frame[:3,3] = np.array(left_translate).reshape(3,)
            # rr.log('left_wrist', rr.Transform3D(translation=left_wrist_frame[:3, 3], mat3x3=left_wrist_frame[:3, :3], axis_length=0.05))
            teleop_core.update_left_hand(left_wrist_frame, np.zeros((24,4,4)))

        right_arm_joints, left_arm_joints = teleop_core.compute_joint_angles()
        teleop_core.log_joint_angles(right_arm_joints, left_arm_joints)
        
    print('Done')
    mse = np.mean(np.array(err)**2)
    print(f'MSE: {mse}')
    rr.log('mse', rr.Scalars(mse), static=True)

main()
