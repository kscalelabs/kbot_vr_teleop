"""

.. code-block:: bash

    # Usage
    ./isaaclab.sh -p isaac_lab_main.py

"""

"""Launch Isaac Sim Simulator first."""


import argparse

from isaaclab.app import AppLauncher

# create argparser
parser = argparse.ArgumentParser(description="Tutorial on creating an empty stage.")
parser.add_argument("--num_envs", type=int, default=16, help="Number of environments to spawn.")
parser.add_argument("--load_checkpoint", type=str, default=None, help="Number of environments to spawn.")
# append AppLauncher cli args
AppLauncher.add_app_launcher_args(parser)
# parse the arguments
args_cli = parser.parse_args()
# launch omniverse app
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

from isaaclab.actuators import ImplicitActuatorCfg
from isaaclab.assets import AssetBaseCfg, Articulation, RigidObjectCfg, RigidObject
from isaaclab.assets.articulation import ArticulationCfg
from isaaclab.sim import SimulationCfg, SimulationContext
import isaacsim.core.utils.prims as prim_utils
from isaaclab.sim.utils import attach_stage_to_usd_context

import isaaclab.sim as sim_utils
from isaaclab.utils.assets import ISAAC_NUCLEUS_DIR
import isaacsim.core.utils.stage as stage_utils
import torch

from isaaclab.utils.noise import AdditiveUniformNoiseCfg as Unoise

from pathlib import Path
from isaaclab.utils import configclass
import isaaclab.envs.mdp as mdp
from isaaclab.envs import ManagerBasedRLEnv, ManagerBasedRLEnvCfg
from isaaclab.managers import EventTermCfg as EventTerm
from isaaclab.managers import CurriculumTermCfg as CurrTerm
from isaaclab.managers import ObservationGroupCfg as ObsGroup
from isaaclab.managers import ObservationTermCfg as ObsTerm
from isaaclab.managers import RewardTermCfg as RewTerm
from isaaclab.managers import TerminationTermCfg as DoneTerm
from isaaclab.managers import SceneEntityCfg
from isaaclab.scene import InteractiveSceneCfg

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import CheckpointCallback
from stable_baselines3.common.logger import configure
from stable_baselines3.common.vec_env import VecNormalize

from datetime import datetime
import os
from isaaclab_rl.sb3 import Sb3VecEnvWrapper, process_sb3_cfg
import skrl
from isaaclab_rl.skrl import SkrlVecEnvWrapper
from skrl.utils.runner.torch import Runner

from isaaclab.utils.math import quat_apply

so101_usd_path = Path(__file__).parent / 'models/SO101/so101_new_calib/so101_new_calib.usd'

joint_names = [
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
]

SO101_CONFIG = ArticulationCfg(
    spawn=sim_utils.UsdFileCfg(
        usd_path=str(so101_usd_path),
        rigid_props=sim_utils.RigidBodyPropertiesCfg(
            disable_gravity=False,
        ),
        articulation_props=sim_utils.ArticulationRootPropertiesCfg(
            enabled_self_collisions=True, solver_position_iteration_count=8, solver_velocity_iteration_count=0
        ),
    ),
    init_state=ArticulationCfg.InitialStateCfg(
        joint_pos={
            key: 0.0 for key in joint_names
        },
        pos=(0.0, 0.0, 0.0),
    ),
    actuators={
        'default_config': ImplicitActuatorCfg(
            joint_names_expr=joint_names,
            effort_limit_sim=2.9, # 30 kg-cm ~= 2.9 Nm
            velocity_limit_sim=4.3, # 0.24 s / 60 deg ~= 4.3 rad/s
            stiffness=10000.0, # default values from tutorial
            damping=100.0,
        ) 
    },
)

@configclass
class ActionsCfg:
    """Action specifications for the environment."""

    joint_efforts = mdp.JointPositionToLimitsActionCfg(asset_name="robot", joint_names=joint_names, scale=1.0)

@configclass
class TerminationsCfg:
    """Termination terms for the MDP."""

    # (1) Time out
    time_out = DoneTerm(func=mdp.time_out, time_out=True)

@configclass
class ObservationsCfg:
    """Observation specifications for the environment."""

    @configclass
    class PolicyCfg(ObsGroup):
        """Observations for policy group."""

        # observation terms (order preserved)

        cube1_pos = ObsTerm(
            func=mdp.root_pos_w,
            params={"asset_cfg": SceneEntityCfg("cube1")},
        )
        cube2_pos = ObsTerm(
            func=mdp.root_pos_w,
            params={"asset_cfg": SceneEntityCfg("cube2")},
        )
        cube1_quat = ObsTerm(
            func=mdp.root_quat_w,
            params={"asset_cfg": SceneEntityCfg("cube1")},
        )
        cube2_quat = ObsTerm(
            func=mdp.root_quat_w,
            params={"asset_cfg": SceneEntityCfg("cube2")},
        )

        joint_pos = ObsTerm(func=mdp.joint_pos_rel, noise=Unoise(n_min=-0.01, n_max=0.01))
        actions = ObsTerm(func=mdp.last_action)

        def __post_init__(self) -> None:
            self.enable_corruption = False
            self.concatenate_terms = True

    # observation groups
    policy: PolicyCfg = PolicyCfg()


x_range = (0.1, 0.3)
y_range = (-0.2, 0.2)

@configclass
class EventCfg:
    """Configuration for events."""

    # on reset
    reset_joint_positions = EventTerm(
        func=mdp.reset_joints_by_offset,
        mode="reset",
        params={
            "asset_cfg": SceneEntityCfg("robot", joint_names=joint_names),
            "position_range": (0.0, 0.0),
            "velocity_range": (0.0, 0.0),
        },
    )

    reset_cube1_position = EventTerm(
        func=mdp.reset_root_state_uniform,
        mode="reset",
        params={
            "asset_cfg": SceneEntityCfg("cube1"),
            "pose_range": {
                'x': x_range,
                'y': y_range,
                'z': (0.1, 0.1),
            },
            "velocity_range": {}
        },
    )

    reset_cube2_position = EventTerm(
        func=mdp.reset_root_state_uniform,
        mode="reset",
        params={
            "asset_cfg": SceneEntityCfg("cube2"),
            "pose_range": {
                'x': x_range,
                'y': y_range,
                'z': (0.15, 0.15),
            },
            "velocity_range": {}
        },
    )

def distance_reward_fn(env: ManagerBasedRLEnv, std: float|None) -> torch.Tensor:
    # extract the used quantities (to enable type-hinting)
    robot_asset: Articulation = env.scene['robot']
    gripper_index = robot_asset.find_bodies('gripper_link')[0][0]
    cube_asset: RigidObject = env.scene['cube1']
    cube_position = cube_asset.data.body_link_pos_w[:, 0, :]  # Shape: [num_envs, 3]

    # Get the position in world frame
    gripper_link_position = robot_asset.data.body_link_pos_w[:, gripper_index, :]  # Shape: [num_envs, 3]
    gripper_link_quat = robot_asset.data.body_link_quat_w[:, gripper_index, :]  # Shape: [num_envs, 4]
    gripper_to_grasp_local_frame = torch.tile(torch.tensor([[0.0, 0.0, -0.08]], device=gripper_link_position.device), (gripper_link_position.shape[0], 1))
    grasp_location = gripper_link_position + quat_apply(gripper_link_quat, gripper_to_grasp_local_frame)

    distance = torch.linalg.vector_norm(grasp_location - cube_position, axis=1)
    if std is None:
        return -distance
    ret = (1 - torch.tanh(distance / std))
    return ret

def orientation_reward_fn(env: ManagerBasedRLEnv) -> torch.Tensor:
    # keep the gripper sideways
    robot_asset: Articulation = env.scene['robot']
    gripper_index = robot_asset.find_bodies('gripper_link')[0][0]
    cube_asset: RigidObject = env.scene['cube1']

    # get transformed (0,1,0) vector and use dot product with (0,0,1) vector to get reward

    gripper_link_quat = robot_asset.data.body_link_quat_w[:, gripper_index, :]  # Shape: [num_envs, 4] 
    y_axis_vecs = torch.tile(torch.tensor([[0.0, 0.1, 0.0]], device=gripper_link_quat.device), (gripper_link_quat.shape[0], 1))
    transformed_vector = quat_apply(gripper_link_quat, y_axis_vecs)
    ret = (transformed_vector @ torch.tensor([0.0,0.0,1.0], device=gripper_link_quat.device)) ** 2
    return ret

def cube_height_reward_fn(env: ManagerBasedRLEnv) -> torch.Tensor:
    """Reward for the cube height."""
    # extract the used quantities (to enable type-hinting)
    cube_asset: RigidObject = env.scene['cube1']
    cube_height = cube_asset.data.root_pos_w[:, 2]  # Shape: [num_envs]
    # reward is the height of the cube
    return cube_height

@configclass
class RewardsCfg:
    """Reward terms for the MDP."""
    gripper_position_coarse = RewTerm(
        func=distance_reward_fn,
        params={"std": 0.3},
        weight=16.0
    )

    gripper_position_fine = RewTerm(
        func=distance_reward_fn,
        params={"std": 0.05},
        weight=10.0
    )

    # gripper_orientation_fine = RewTerm(
    #     func=orientation_reward_fn,
    #     weight=3.0
    # )

    action_rate = RewTerm(func=mdp.action_rate_l2, weight=-1e-3)

    joint_vel = RewTerm(
        func=mdp.joint_vel_l2,
        params={"asset_cfg": SceneEntityCfg("robot")},
        weight=-1e-4,
    )

    arm_joint_effort = RewTerm(
        func=mdp.joint_torques_l2,
        params={"asset_cfg": SceneEntityCfg("robot", joint_names=list(filter(lambda x: x != 'gripper', joint_names)))},
        weight=-1e-1,
    )

    cube_height = RewTerm(
        func=cube_height_reward_fn,
        weight=1.0,
    )

@configclass
class CurriculumCfg:
    """Curriculum terms for the MDP."""

    action_rate = CurrTerm(
        func=mdp.modify_reward_weight, params={"term_name": "action_rate", "weight": -1e-1, "num_steps": 10000}
    )

    joint_vel = CurrTerm(
        func=mdp.modify_reward_weight, params={"term_name": "joint_vel", "weight": -1e-1, "num_steps": 10000}
    )

    arm_joint_effort = CurrTerm(
        func=mdp.modify_reward_weight, params={"term_name": "arm_joint_effort", "weight": -1, "num_steps": 10000}
    )

    cube_height_increase = CurrTerm(
        func=mdp.modify_reward_weight, params={"term_name": "cube_height", "weight": 10, "num_steps": 10000}
    )

cube_size = 0.03
class SO101SceneCfg(InteractiveSceneCfg):
    """Designs the scene by spawning ground plane, light, objects and meshes from usd files."""
    # ground plane with physics
    ground = AssetBaseCfg(
        prim_path="/World/ground",
        spawn=sim_utils.GroundPlaneCfg(
            size=(100.0, 100.0),
        ),
    )

    # cartpole
    robot: ArticulationCfg = SO101_CONFIG.replace(prim_path="{ENV_REGEX_NS}/Robot")

    # lights
    dome_light = AssetBaseCfg(
        prim_path="/World/DomeLight",
        spawn=sim_utils.DomeLightCfg(color=(0.9, 0.9, 0.9), intensity=500.0),
    )

    # cube with physics
    cube1 = RigidObjectCfg(
        prim_path="{ENV_REGEX_NS}/cube1",
        spawn=sim_utils.CuboidCfg(
            size=(cube_size, cube_size, cube_size),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(),
            mass_props= sim_utils.MassPropertiesCfg(mass=0.1),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.0, 1.0, 0.0)),
            physics_material=sim_utils.RigidBodyMaterialCfg(),
            collision_props= sim_utils.CollisionPropertiesCfg(
                collision_enabled=True,
            )
        )
    )

    cube2 = RigidObjectCfg(
        prim_path="{ENV_REGEX_NS}/cube2",
        spawn=sim_utils.CuboidCfg(
            size=(cube_size, cube_size, cube_size),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(),
            mass_props= sim_utils.MassPropertiesCfg(mass=0.1),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(1.0, 0.2, 0.0)),
            physics_material=sim_utils.RigidBodyMaterialCfg(),
            collision_props= sim_utils.CollisionPropertiesCfg(
                collision_enabled=True,
            )
        )
    )


@configclass
class SO101EnvCfg(ManagerBasedRLEnvCfg):
    """Configuration for the cartpole environment."""

    # Scene settings
    scene = SO101SceneCfg(num_envs=1024, env_spacing=2.5)
    # Basic settings
    observations = ObservationsCfg()
    actions = ActionsCfg()
    events = EventCfg()
    rewards: RewardsCfg = RewardsCfg()
    terminations: TerminationsCfg = TerminationsCfg()
    curriculum: CurriculumCfg = CurriculumCfg()

    def __post_init__(self):
        """Post initialization."""
        # viewer settings
        self.viewer.eye = [4.5, 0.0, 6.0]
        self.viewer.lookat = [0.0, 0.0, 2.0]
        # general settings
        self.decimation = 3
        self.episode_length_s = 10
        # simulation settings
        self.sim.dt = 1 / 60
        self.sim.render_interval = 2

        # copied from isaac lab franka arm stack example
        self.sim.physx.bounce_threshold_velocity = 0.2
        self.sim.physx.bounce_threshold_velocity = 0.01
        self.sim.physx.gpu_found_lost_aggregate_pairs_capacity = 1024 * 1024 * 4
        self.sim.physx.gpu_total_aggregate_pairs_capacity = 16 * 1024
        self.sim.physx.friction_correlation_distance = 0.00625


def main():
    """Main function."""
    # parse the arguments
    env_cfg = SO101EnvCfg()
    env_cfg.scene.num_envs = args_cli.num_envs
    env_cfg.sim.device = args_cli.device
    checkpoint_path = args_cli.load_checkpoint
    env_cfg.sim.create_stage_in_memory = True
    # setup base environment
    env = ManagerBasedRLEnv(cfg=env_cfg)
    run_info = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_root_path = os.path.abspath(os.path.join("logs", "sb3", 'so101'))
    log_dir = os.path.join(log_root_path, run_info)
    print(f"[INFO] Logging experiment in directory: {log_root_path}")
    print(f"Exact experiment name requested from command line: {run_info}")

    env = SkrlVecEnvWrapper(env)
    runner = Runner(
        env = env,
        cfg = Runner.load_cfg_from_yaml('skrl_config.yaml'),
    )

    if checkpoint_path is not None:
        runner.agent.load(checkpoint_path)

    runner.run()


    # env = Sb3VecEnvWrapper(env)
    # # create agent from stable baselines
    # agent = PPO('MlpPolicy', env, verbose=1, device='cpu')
    # new_logger = configure(log_dir, ["stdout", "tensorboard"])
    # agent.set_logger(new_logger)
    # checkpoint_callback = CheckpointCallback(save_freq=1000, save_path=log_dir, name_prefix="model", verbose=2)
    # agent.learn(total_timesteps=100_000_000, callback=checkpoint_callback, log_interval=1)
   
    env.close()


if __name__ == "__main__":
    # run the main function
    main()
    # close sim app
    simulation_app.close()
