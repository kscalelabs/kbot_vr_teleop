import rerun as rr
import numpy as np
from pathlib import Path
from tqdm import tqdm
from line_profiler import profile
from kscale_vr_teleop.teleop_core import TeleopCore
import warnings
import pyarrow as pa

rr.init("replay_teleop_from_rerun", spawn=True)

recording_path = "/home/miller/Downloads/data.rrd"
recording = rr.dataframe.load_recording(str(recording_path))
view = recording.view(index="log_time", contents="/**")
reader = view.select()

teleop_core = TeleopCore()
teleop_core.update_head(np.eye(4))

rr.log('origin_axes', rr.Transform3D(translation=[0,0,0], axis_length=0.1), static=True)

err = []
@profile
def main():
    left_wrist_frame = np.eye(4)
    right_wrist_frame = np.eye(4)

    # Iterate over RecordBatchReader batches and rows
    batch_reader = view.select()
    total_rows = 0
    for batch in batch_reader:
        table = pa.Table.from_batches([batch])
        columns = table.column_names
        for i in range(table.num_rows):
            row = {col: table[col][i].as_py() for col in columns}
            timestamp = row.get('log_time') if 'log_time' in row else None
            if timestamp is None:
                warnings.warn(f"Skipping row {total_rows} with missing log_time")
                timestamp = int(total_rows)
            rr.set_time('', timestamp=timestamp)
            right_translate = row.get('/right_wrist:Transform3D:translation')
            right_rot = row.get('/right_wrist:Transform3D:mat3x3')
            left_translate = row.get('/left_wrist:Transform3D:translation')
            left_rot = row.get('/left_wrist:Transform3D:mat3x3')

            if right_rot is not None:
                right_wrist_frame[:3,:3] = np.array(right_rot).reshape((3,3))
                right_wrist_frame[:3,3] = np.array(right_translate).reshape(3,)
                teleop_core.update_right_hand(right_wrist_frame, np.zeros((24,4,4)))
            if left_rot is not None:
                left_wrist_frame[:3,:3] = np.array(left_rot).reshape((3,3))
                left_wrist_frame[:3,3] = np.array(left_translate).reshape(3,)
                teleop_core.update_left_hand(left_wrist_frame, np.zeros((24,4,4)))

            right_arm_joints, left_arm_joints = teleop_core.compute_joint_angles()
            teleop_core.log_joint_angles(right_arm_joints, left_arm_joints)
            total_rows += 1

    print('Done')
    mse = np.mean(np.array(err)**2)
    print(f'MSE: {mse}')
    rr.log('mse', rr.Scalars(mse), static=True)

main()
