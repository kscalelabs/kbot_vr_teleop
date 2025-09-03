import carb
from isaacsim import SimulationApp
import sys

BACKGROUND_STAGE_PATH = "/background"
BACKGROUND_USD_PATH = "/Isaac/Environments/Grid/default_environment.usd"


CONFIG = {"renderer": "RayTracedLighting", "headless": False}

# Example ROS2 bridge sample demonstrating the manual loading of stages and manual publishing of images
simulation_app = SimulationApp(CONFIG)
import omni
import numpy as np
from isaacsim.core.api import SimulationContext
from isaacsim.core.utils import stage, extensions, nucleus
import omni.graph.core as og
import omni.replicator.core as rep
import omni.syntheticdata._syntheticdata as sd

from isaacsim.core.utils.prims import set_targets
from isaacsim.sensors.camera import Camera
import isaacsim.core.utils.numpy.rotations as rot_utils
from isaacsim.core.utils.prims import is_prim_path_valid
from isaacsim.core.nodes.scripts.utils import set_target_prims

# Enable ROS2 bridge extension
extensions.enable_extension("isaacsim.ros2.bridge")

simulation_app.update()

simulation_context = SimulationContext(stage_units_in_meters=1.0)

# Locate Isaac Sim assets folder to load environment and robot stages
assets_root_path = nucleus.get_assets_root_path()
if assets_root_path is None:
    carb.log_error("Could not find Isaac Sim assets folder")
    simulation_app.close()
    sys.exit()

# Loading the environment
stage.add_reference_to_stage(assets_root_path + BACKGROUND_USD_PATH, BACKGROUND_STAGE_PATH)


###### Camera helper functions for setting up publishers. ########

# Paste functions from the tutorial here
# def publish_camera_tf(camera: Camera): ...
# def publish_camera_info(camera: Camera, freq): ...
# def publish_pointcloud_from_depth(camera: Camera, freq): ...
# def publish_depth(camera: Camera, freq): ...
# def publish_rgb(camera: Camera, freq): ...
def publish_rgb(camera: Camera, freq):
    # The following code will link the camera's render product and publish the data to the specified topic name.
    render_product = camera._render_product_path
    step_size = int(60/freq)
    topic_name = camera.name+"_rgb"
    queue_size = 1
    node_namespace = ""
    frame_id = camera.prim_path.split("/")[-1] # This matches what the TF tree is publishing.

    rv = omni.syntheticdata.SyntheticData.convert_sensor_type_to_rendervar(sd.SensorType.Rgb.name)
    writer = rep.writers.get(rv + "ROS2PublishImage")
    writer.initialize(
        frameId=frame_id,
        nodeNamespace=node_namespace,
        queueSize=queue_size,
        topicName=topic_name
    )
    writer.attach([render_product])

    # Set step input of the Isaac Simulation Gate nodes upstream of ROS publishers to control their execution rate
    gate_path = omni.syntheticdata.SyntheticData._get_node_path(
        rv + "IsaacSimulationGate", render_product
    )
    og.Controller.attribute(gate_path + ".inputs:step").set(step_size)

    return

###################################################################

# Create a Camera prim. Note that the Camera class takes the position and orientation in the world axes convention.
camera = Camera(
    prim_path="/World/floating_camera",
    position=np.array([-3.11, -1.87, 1.0]),
    frequency=20,
    resolution=(256, 256),
    orientation=rot_utils.euler_angles_to_quats(np.array([0, 0, 0]), degrees=True),
)
camera.initialize()

simulation_app.update()
camera.initialize()

############### Calling Camera publishing functions ###############

# Call the publishers.
# Make sure you pasted in the helper functions above, and uncomment out the following lines before running.

approx_freq = 30
#publish_camera_tf(camera)
#publish_camera_info(camera, approx_freq)
publish_rgb(camera, approx_freq)
#publish_depth(camera, approx_freq)
#publish_pointcloud_from_depth(camera, approx_freq)

####################################################################

# Initialize physics
simulation_context.initialize_physics()
simulation_context.play()

while simulation_app.is_running():
    simulation_context.step(render=True)

simulation_context.stop()
simulation_app.close()