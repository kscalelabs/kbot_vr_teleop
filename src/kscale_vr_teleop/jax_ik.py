from urdf_parser_py import urdf as urdf_parser
from pathlib import Path
import jax
import jax.numpy as np
from jax.scipy.spatial.transform import Rotation
import jaxopt

from kscale_vr_teleop._assets import ASSETS_DIR


class RobotInverseKinematics:
    def __init__(self, filepath: str) -> None:
        urdf_contents = open(filepath, 'r').read()
        urdf_parent_path =Path(filepath).absolute().parent
        urdf_contents = urdf_contents.replace('filename="', f'filename="{urdf_parent_path}/')
        self.urdf: urdf_parser.Robot = urdf_parser.URDF.from_xml_string(urdf_contents)

    @staticmethod
    def make_transform_mat(joint: urdf_parser.Joint, joint_angle: float) -> np.ndarray:
        '''
        Create a 4x4 transformation matrix from the parent to child link
        Only works for fixed and revolute joints currently
        '''
        origin_position = joint.origin.position
        origin_rotation = Rotation.from_euler('XYZ', joint.origin.rotation) # TODO: verify the rotation assumption is correct
        mat = np.eye(4)
        mat = mat.at[:3,3].set(origin_position)
        mat = mat.at[:3,:3].set(origin_rotation.as_matrix())
        if joint.joint_type == 'fixed':
            return mat
        elif joint.joint_type == 'revolute':
            rot_axis = np.array(joint.axis)
            rot_mat = Rotation.from_rotvec(joint_angle * rot_axis).as_matrix()
            rot_mat_4x4 = np.eye(4)
            rot_mat_4x4 = rot_mat_4x4.at[:3,:3].set(rot_mat)
            return rot_mat_4x4 @ mat
        else:
            raise NotImplementedError(f"Joint type {joint.joint_type} not supported")

    def inverse_kinematics(self, ee_links: list[str], transform_targets: np.ndarray):
        '''
        transform_targets is Nx4x4 
        ee_links is N long
        '''

        base_link_name = 'base'

        # build up kinematic chains as lists of joints
        kinematic_chain_maps = {'base': []}
        for link_name, child_info_list in self.urdf.child_map.items():
            for (joint_name, child_link_name) in child_info_list:
                kinematic_chain_maps[child_link_name] = kinematic_chain_maps[link_name] + [joint_name]

        @jax.jit
        def forward_kinematics(joint_angles):
            mat = np.eye(4)
            for ee_link_name in ee_links:
                for joint_name in kinematic_chain_maps[ee_link_name]:
                    joint = self.urdf.joint_map[joint_name]
                    joint_index = list(self.urdf.joint_map.keys()).index(joint_name)
                    joint_mat = self.make_transform_mat(joint, joint_angles[joint_index])
                    mat = mat @ joint_mat
            return mat
                
        def residuals(joint_angle_vector):
            end_effector_mats = []
            for transform_target in transform_targets:
                end_effector_mat = forward_kinematics(joint_angle_vector)
                end_effector_mats.append(end_effector_mat)
            return (np.array(end_effector_mats) - np.array(transform_targets)).flatten()

        opt_result = jaxopt.ScipyLeastSquares(fun=residuals, method='lm').run(np.zeros(len(self.urdf.joints)))
        return opt_result

if __name__ == '__main__':
    urdf_path  = str(ASSETS_DIR / "kbot" / "robot.urdf")
    ik_solver = RobotInverseKinematics(urdf_path)
    ik_solver.inverse_kinematics(['KB_C_501X_Right_Bayonet_Adapter_Hard_Stop'], [np.eye(4)])
    ik_solver.inverse_kinematics(['KB_C_501X_Left_Bayonet_Adapter_Hard_Stop'], [np.eye(4)])