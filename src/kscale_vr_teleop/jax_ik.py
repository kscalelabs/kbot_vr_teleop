from urdf_parser_py import urdf as urdf_parser
from pathlib import Path
import jax
# import jax.numpy as np
# from jax.scipy.spatial.transform import Rotation
import numpy as np
from scipy.spatial.transform import Rotation
import jaxopt
from tqdm import tqdm

from kscale_vr_teleop._assets import ASSETS_DIR


class RobotInverseKinematics:
    def __init__(self, filepath: str, ee_links: list[str], base_link_name: str) -> None:
        urdf_contents = open(filepath, 'r').read()
        urdf_parent_path =Path(filepath).absolute().parent
        urdf_contents = urdf_contents.replace('filename="', f'filename="{urdf_parent_path}/')
        self.urdf: urdf_parser.Robot = urdf_parser.URDF.from_xml_string(urdf_contents)

        # build up kinematic chains as lists of joints
        kinematic_chain_maps = {base_link_name: []}
        for link_name, child_info_list in self.urdf.child_map.items():
            for (joint_name, child_link_name) in child_info_list:
                kinematic_chain_maps[child_link_name] = kinematic_chain_maps[link_name] + [joint_name]

        self.active_joints = [
            j for j in self.urdf.joints if j.joint_type != 'fixed'
        ]

        # Create mapping from joint name to active joint index
        self.active_joint_indices = {}
        for i, joint in enumerate(self.active_joints):
            self.active_joint_indices[joint.name] = i

        def forward_kinematics(joint_angles):
            res = []
            for ee_link_name in ee_links:
                mat = np.eye(4)
                for joint_name in kinematic_chain_maps[ee_link_name]:
                    joint = self.urdf.joint_map[joint_name]
                    if joint.joint_type == 'fixed':
                        joint_angle = 0.0
                    else:
                        joint_angle = joint_angles[self.active_joint_indices[joint_name]]
                    joint_mat = self.make_transform_mat(joint, joint_angle)
                    mat = mat @ joint_mat
                res.append(mat)
            return np.array(res)

        # self.forward_kinematics = jax.jit(forward_kinematics)
        self.forward_kinematics = forward_kinematics

        upper_bounds = []
        lower_bounds = []
        for joint in self.urdf.joints:
            if joint.joint_type == 'revolute':
                upper_bounds.append(joint.limit.upper)
                lower_bounds.append(joint.limit.lower)
            # else:
            #     upper_bounds.append(np.inf)
            #     lower_bounds.append(-np.inf)
        self.upper_bounds = np.array(upper_bounds)
        self.lower_bounds = np.array(lower_bounds)
        self.last_solution = np.zeros(len(self.active_joints))
        
                # Pre-compile the residuals function and create the solver once
        # self._setup_ik_solver()

    @staticmethod
    def make_transform_mat(joint: urdf_parser.Joint, joint_angle: float) -> np.ndarray:
        '''
        Create a 4x4 transformation matrix from the parent to child link
        Only works for fixed and revolute joints currently
        '''
        origin_position = joint.origin.position
        origin_rotation_rpy = joint.origin.rotation  # roll, pitch, yaw (X, Y, Z)
        
        # Translation matrix
        T = np.eye(4)
        # T = T.at[:3, 3].set(origin_position)
        T[:3, 3] = origin_position
        
        # Origin rotation matrix (fixed frame: roll around X, pitch around Y, yaw around Z)
        R_origin = np.eye(4)
        if joint.origin.rotation is not None:
            rot_matrix = Rotation.from_euler('xyz', origin_rotation_rpy).as_matrix()
            # R_origin = R_origin.at[:3, :3].set(rot_matrix)
            R_origin[:3, :3] = rot_matrix
        
        if joint.joint_type == 'fixed':
            return T @ R_origin
        elif joint.joint_type == 'revolute':
            # Joint rotation matrix
            rot_axis = np.array(joint.axis)
            joint_rot_mat = Rotation.from_rotvec(joint_angle * rot_axis).as_matrix()
            R_joint = np.eye(4)
            # R_joint = R_joint.at[:3, :3].set(joint_rot_mat)
            R_joint[:3, :3] = joint_rot_mat
            
            # Correct order from test_all_combinations.py: T @ R_origin @ R_joint (no transpose needed)
            result = T @ R_origin @ R_joint
            return result
        else:
            raise NotImplementedError(f"Joint type {joint.joint_type} not supported")

    def _setup_ik_solver(self) -> None:
        """Setup the IK solver with pre-compiled residuals function"""
        
        @jax.jit
        def residuals(joint_angle_vector, transform_targets):
            end_effector_mats = self.forward_kinematics(joint_angle_vector)
            right_ee_position = end_effector_mats[0]
            left_ee_position = end_effector_mats[1]
            right_wrist_mat = transform_targets[0]
            left_wrist_mat = transform_targets[1]
            right_ee_forward = -right_ee_position[:3,2]
            left_ee_forward = left_ee_position[:3,2]
            right_target_forward = -right_wrist_mat[:3, 2]
            left_target_forward = -left_wrist_mat[:3, 2]
            right_ee_up = -right_ee_position[:3, 1]
            left_ee_up = left_ee_position[:3, 1]
            right_target_up = right_wrist_mat[:3,1]
            left_target_up = left_wrist_mat[:3,1]
            
            # Clamp dot products to avoid numerical issues with arccos
            right_dot_forward = np.clip(np.dot(right_ee_forward, right_target_forward), -1.0, 1.0)
            left_dot_forward = np.clip(np.dot(left_ee_forward, left_target_forward), -1.0, 1.0)
            right_dot_up = np.clip(np.dot(right_ee_up, right_target_up), -1.0, 1.0)
            left_dot_up = np.clip(np.dot(left_ee_up, left_target_up), -1.0, 1.0)
            
            right_rotation_angle_off = np.arccos(right_dot_forward)
            left_rotation_angle_off = np.arccos(left_dot_forward)
            right_y_angle_off = np.arccos(right_dot_up)
            left_y_angle_off = np.arccos(left_dot_up)
            
            return np.concatenate([
                right_ee_position[:3, 3] - right_wrist_mat[:3, 3],
                left_ee_position[:3, 3] - left_wrist_mat[:3, 3],
                np.array([0.1*right_rotation_angle_off, 0.1*right_y_angle_off, 0.1*left_rotation_angle_off, 0.1*left_y_angle_off])
            ])
        
        self.residuals = residuals
        
        # Setup Jacobian sparsity pattern
        jac_sparsity_mat = np.zeros((10, len(self.active_joints)))
        # joints: evens are right, odds are left, order is shoulder to wrist
        jac_sparsity_mat = jac_sparsity_mat.at[:3, :8:2].set(1)
        jac_sparsity_mat = jac_sparsity_mat.at[6:8, ::2].set(1)
        jac_sparsity_mat = jac_sparsity_mat.at[3:6, 1:9:2].set(1)
        jac_sparsity_mat = jac_sparsity_mat.at[8:10, 1::2].set(1)
        
        # Create the solver once with sparsity pattern (without bounds for now)
        self.solver = jaxopt.ScipyLeastSquares(
            fun=lambda params, targets: self.residuals(params, targets),
            method='lm',
            options={
                'jac_sparsity': jac_sparsity_mat,
            }
        )

    def inverse_kinematics(self, transform_targets: np.ndarray):
        '''
        transform_targets is Nx4x4 
        ee_links is N long
        '''
        # Convert to JAX array if needed
        transform_targets = np.array(transform_targets)
        
        # Run the pre-compiled solver
        opt_result, _opt_info = self.solver.run(
            self.last_solution, 
            transform_targets
        )
        
        # Update last solution for warm starting
        self.last_solution = opt_result
        return opt_result

if __name__ == '__main__':
    urdf_path  = str(ASSETS_DIR / "kbot" / "robot.urdf")
    ik_solver = RobotInverseKinematics(urdf_path, ['KB_C_501X_Right_Bayonet_Adapter_Hard_Stop', 'KB_C_501X_Left_Bayonet_Adapter_Hard_Stop'], 'base')
    for i in tqdm(range(1000)):
        ik_solver.inverse_kinematics([np.eye(4), np.eye(4)])