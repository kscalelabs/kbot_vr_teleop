import numpy as np
from vuer import Vuer, VuerSession
import asyncio
from vuer.schemas import ImageBackground, Hands
import cv2

cam_mat = np.array([[266.61728276,0.,643.83126137],[0.,266.94450686,494.81811813],[0.,0.,1.,]])
dist_coeffs = np.array([[-6.07417419e-02,9.95447444e-02,-2.26448001e-04,1.22881804e-03,3.42134205e-03,1.45361886e-01,8.03248099e-02,2.11170107e-02,-3.80620047e-03,2.48350591e-05,-8.33565666e-04,2.97806723e-05]])

async def stream_cameras(session: VuerSession):
    left_pipeline = "libcamerasrc camera-name=/base/axi/pcie@1000120000/rp1/i2c@80000/ov5647@36 exposure-time-mode=0 analogue-gain-mode=0 ae-enable=true awb-enable=true af-mode=manual ! video/x-raw,format=BGR,width=1280,height=720,framerate=30/1 ! videoconvert ! appsink drop=1 max-buffers=1"
    right_pipeline = "libcamerasrc camera-name=/base/axi/pcie@1000120000/rp1/i2c@88000/ov5647@36 exposure-time-mode=0 analogue-gain-mode=0 ae-enable=true awb-enable=true af-mode=manual ! video/x-raw,format=BGR,width=1280,height=720,framerate=30/1 ! videoconvert ! appsink drop=1 max-buffers=1"
    cam_left = cv2.VideoCapture(left_pipeline, cv2.CAP_GSTREAMER)
    cam_right = cv2.VideoCapture(right_pipeline, cv2.CAP_GSTREAMER)
    

    while True:
        ret_left, frame_left = cam_left.read()
        ret_right, frame_right = cam_right.read()
        if not ret_left or not ret_right:
            continue
        frame_left_rgb = cv2.cvtColor(frame_left, cv2.COLOR_BGR2RGB)
        # frame_right_rgb = cv2.cvtColor(frame_right, cv2.COLOR_BGR2RGB)
        frame_left_rgb = cv2.undistort(frame_left_rgb, cam_mat, dist_coeffs)
        frame_left_rgb = cv2.resize(frame_left_rgb, (640, 360), interpolation=cv2.INTER_LINEAR)
        frame_right_rgb = frame_left_rgb.copy()
        # frame_right_rgb = cv2.undistort(frame_right_rgb, cam_mat, dist_coeffs)
        # Add text labels for left/right cameras
        # cv2.putText(frame_left_rgb, "Left Camera", (600, 30), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 4)
        # cv2.putText(frame_right_rgb, "Right Camera", (600, 30), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 4)
        # Send both images as ImageBackground objects for left/right eye
        interpupilary_dist = 0

        distance_to_camera = 3.5*cam_mat[0][0] / frame_left_rgb.shape[1] # TODO: remove this hard-coded 2 multiplier
        vertical_angle_rad = np.deg2rad(25)  # Example vertical angle, adjust as needed
        # Calculate positions for left and right screens with vertical displacement
        # Keep the same distance from user but move down by the vertical angle
        y_offset = -distance_to_camera * np.sin(vertical_angle_rad)  # Negative for below horizon
        z_offset = distance_to_camera * (np.cos(vertical_angle_rad) - 1)  # Adjustment to maintain distance
        session.upsert([
            ImageBackground(
                frame_left_rgb,
                aspect=1.778,
                height=2,
                distanceToCamera=distance_to_camera,
                position=[-interpupilary_dist/2, y_offset, z_offset],
                layers=1,
                format="jpeg",
                quality=1000,
                key="background-left",
                interpolate=True,
            ),
            ImageBackground(
                frame_right_rgb,
                aspect=1.778,
                height=2,
                distanceToCamera=distance_to_camera,
                position=[-interpupilary_dist/2, y_offset, z_offset],
                layers=2,
                format="jpeg",
                quality=1000,
                key="background-right",
                interpolate=True,
            ),
        ], to="bgChildren")
        await asyncio.sleep(1/30)  # ~30 FPS for smoother streaming