import numpy as np
from scipy.spatial.transform import Rotation

from kscale_vr_teleop.util import fast_mat_inv
from kscale_vr_teleop.teleop_core import TeleopCore
from kscale_vr_teleop.finger_udp_server import FingerUDPHandler

kbot_xr_to_urdf_frame = np.array([
    [0,  0, -1,  0],  # Robot X-axis = -VR Z-axis (flip forward/back)
    [-1, 0,  0,  0],  # Robot Y-axis = -VR X-axis (flip left/right)
    [0,  1,  0,  0],  # Robot Z-axis = +VR Y-axis (keep up direction)
    [0,  0,  0,  1]   # Homogeneous coordinate
], dtype=np.float32)

hand_xr_to_urdf_frame = np.array([
    [0, 1, 0, 0],  # Rotate hand frame: X-axis → Y-axis
    [0, 0, 1, 0],  # Rotate hand frame: Y-axis → Z-axis
    [1, 0, 0, 0],  # Rotate hand frame: Z-axis → X-axis
    [0, 0, 0, 1]   # Homogeneous coordinate
], dtype=np.float32)

class TrackingHandler:
    def __init__(self, websocket, udp_host, ik_solver=None, udp_port=10000):
        self.udp_host = udp_host
        self.udp_port = udp_port

        self.teleop_core = TeleopCore(websocket, udp_host, udp_port, ik_solver)
        self.finger_server = FingerUDPHandler(udp_host=udp_host, udp_port=10001)
    
    def _handle_target_location(self, tracking_data, side, tracking_type):
        '''
        Handles the wrist/controller target location matrix (always present).
        Converts from flat 16-element array to 4x4 matrix and applies frame transformations.
        '''
        # Extract and convert matrix (column-major from JS)
        target_matrix_flat = np.array(tracking_data['targetLocation'], dtype=np.float32)
        target_matrix = target_matrix_flat.reshape(4, 4).T  # Transpose for column-major to row-major
        
        # Rotate controller matrix 90 degrees around Z-axis for gripper alignment
        if tracking_type == "controller":
            direction = -1 if side == 'right' else 1
            rotation = Rotation.from_euler('z', 90 * direction, degrees=True)
            rotation_matrix = rotation.as_matrix()
            # Apply rotation to the orientation part
            target_matrix[:3, :3] = target_matrix[:3, :3] @ rotation_matrix
        
        # Apply frame transformation to robot coordinate system
        wrist_mat = kbot_xr_to_urdf_frame @ target_matrix
        
        self.teleop_core.update_target_location(side, wrist_mat)
        
    def _handle_joints(self, tracking_data, side):
        '''
        Handles finger joint data for hand tracking.
        joints_data is 384 floats (24 finger joints × 16 matrix elements)
        '''
        joints_data = tracking_data.get("joints", None)
        if joints_data is None or len(joints_data) == 0:
            return
        
        # Get the wrist matrix that was already processed
        wrist_mat = self.teleop_core.left_wrist_pose if side == 'left' else self.teleop_core.right_wrist_pose
        # Convert finger joints: 384 elements (24 joints × 16)
        finger_joints_flat = np.array(joints_data, dtype=np.float32)
        finger_mat_numpy = finger_joints_flat.reshape(24, 4, 4).transpose((0, 2, 1))
        
        # Get original wrist in VR space by inverting robot transform
        wrist_vr = np.linalg.inv(kbot_xr_to_urdf_frame) @ wrist_mat
        
        # Make finger poses relative to wrist in robot frame
        finger_poses = (hand_xr_to_urdf_frame @ fast_mat_inv(wrist_vr) @ finger_mat_numpy.T).T
        self.teleop_core.update_joints(side, finger_poses)
    
    def _handle_buttons(self, tracking_data, side):
        '''
        Handles controller button and joystick data.
        Updates controller state with gripper value and joystick positions.
        '''
        # Extract controller data
        gripper_value = tracking_data.get('trigger', 0.0)
        joystick_x = tracking_data.get('joystickX', 0.0)
        joystick_y = tracking_data.get('joystickY', 0.0)
        
        self.teleop_core.update_buttons(side, gripper_value, joystick_x, joystick_y)

    async def handle_tracking(self, event):
        '''
        Handles unified tracking data structure.
        Always processes targetLocation, then handles joints (hand) or buttons (controller).
        '''
        tracking_type = event.get("type", None)
        
        for side in ["left", "right"]:
            tracking_data = event.get(side, None)
            if tracking_data is not None:
                self._handle_target_location(tracking_data, side, tracking_type)
                self._handle_buttons(tracking_data, side)      
                self._handle_joints(tracking_data, side)

        await self.teleop_core.compute_and_send_joints()

        # Send finger commands via new UDP server
        # self.finger_server.send_finger_commands(right_finger_angles, left_finger_angles)
