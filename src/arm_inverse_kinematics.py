from kscale_vr_teleop.arm_inverse_kinematics import *

# Backwards compatibility shim

class IKSolver:
    def __init__(self, robot: URDF):
        self.robot = robot
        self.last_guess = np.zeros(len(robot.actuated_joints)//2)
        self.lower_bounds = []
        self.upper_bounds = []
        for joint in self.robot.actuated_joints[::2]:
            self.lower_bounds.append(joint.limit.lower)
            self.upper_bounds.append(joint.limit.upper)

    def from_scratch_ik(self, target_position, frame_name, initial_guess = None): # This shouldn't be necessary but ikpy's inverse kinematics is ironically crap
        # placeholder = np.zeros(10)
        # if initial_guess is not None: # TODO: refactor or remove this ugly code
        #     placeholder[::2] = initial_guess
        #     initial_guess = np.clip(placeholder, self.lower_bounds, self.upper_bounds)
        config_base = {
                k.name: 0 for k in self.robot.actuated_joints[1::2]
            }
        def residuals(joint_angles):
            config_update = {
                k.name: joint_angles[i] for i, k in enumerate(self.robot.actuated_joints[::2])
            }
            config_base.update(config_update)
            self.robot.update_cfg(config_base)
            ee_position = self.robot.get_transform(frame_name, "base")
            return ee_position[:3, 3] - target_position
        
        jac_sparsity_mat = np.zeros((1, len(self.robot.actuated_joints)//2))
        jac_sparsity_mat[0,0] = 1
        jac_sparsity_mat[0,1] = 1
        jac_sparsity_mat[0,2] = 1
        jac_sparsity_mat[0,3] = 1

        SOLVE_WITH_BOUNDS = True
        result = least_squares(
            residuals, 
            self.last_guess, 
            # np.zeros(5),
            bounds=(self.lower_bounds, self.upper_bounds) if SOLVE_WITH_BOUNDS else (-np.inf, np.inf), 
            jac_sparsity=np.repeat(jac_sparsity_mat, 3, axis=0),
            # ftol=1e-2,
            # gtol = 1e-2,
            # xtol=1e-4
        )
        solution = result.x
        self.last_guess = solution
        # if not SOLVE_WITH_BOUNDS:
        #     solution = np.clip(solution, self.lower_bounds, self.upper_bounds)
        return solution


file_absolute_parent = Path(__file__).parent.absolute()

urdf_path  = f"{file_absolute_parent}/assets/kbot/robot.urdf"

right_chain = ikpy.chain.Chain.from_urdf_file(
    urdf_path,
    base_elements=['base'],  # Start from the torso and let ikpy auto-discover
    # base_element_type='joint'
)

def make_robot():
    return URDF.load(
            urdf_path,
            build_scene_graph=True,      # Enable forward kinematics
            build_collision_scene_graph=False,  # Optional: for collision checking
            load_collision_meshes=False,
            load_meshes=True
        )
    
arms_robot = make_robot()

VISUALIZE = False

if VISUALIZE:
    visualizer = ThreadedRobotVisualizer(make_robot)
    visualizer.start_viewer()
    visualizer.add_marker('goal', [0.,0.,0.])


# left_chain = ikpy.chain.Chain.from_urdf_file(
#     f"{file_absolute_parent}/assets/kbot/robot.urdf",
#     base_elements=['Torso_Side_Left']  # Start from the torso and let ikpy auto-discover
#     base_element_type='joint'
# )

solver = IKSolver(arms_robot)

def calculate_arm_joints(head_mat, left_wrist_mat, right_wrist_mat, initial_guess=None):
    # right_wrist_mat = right_wrist_mat.copy()
    # right_wrist_mat[:3, 3] += np.array([0,0,-1.5]) # move down to roughly match urdf coordinate system

    right_joint_angles = solver.from_scratch_ik(target_position=right_wrist_mat[:3,3], frame_name = 'KB_C_501X_Right_Bayonet_Adapter_Hard_Stop', initial_guess = initial_guess)
    # right_joint_angles = solver.from_scratch_ik(target_position=right_wrist_mat[:3,3])
    new_config={
        k.name: right_joint_angles[i] for i, k in enumerate(arms_robot.actuated_joints[::2])
    }
    arms_robot.update_cfg(new_config)
    if VISUALIZE:
        visualizer.update_marker('goal', right_wrist_mat[:3, 3], right_wrist_mat[:3, :3])
        visualizer.update_config(new_config)
    # print(right_wrist_mat[:3, 3], arms_robot.get_transform('KB_C_501X_Right_Bayonet_Adapter_Hard_Stop', 'base')[:3,3])

    return np.zeros(5), right_joint_angles

def new_calculate_arm_joints(head_mat, left_wrist_mat, right_wrist_mat):
    # right_wrist_mat[:3, 3] += np.array([0,0,-1.5]) # move down to roughly match urdf coordinate system
    ik_solution = right_chain.inverse_kinematics(target_position = right_wrist_mat[:3, 3])

    new_config={
        k.name: ik_solution[1:-1][i//2] for i, k in enumerate(arms_robot.actuated_joints)
    }
    arms_robot.update_cfg(new_config)
    # if VISUALIZE:
    #     visualizer.update_marker('goal', right_wrist_mat[:3, 3], right_wrist_mat[:3, :3])
    #     visualizer.update_config(new_config)

    return np.zeros(5), ik_solution  # ikpy includes dummy links on both ends of the kinematic chain



import mujoco as mj
from mujoco import mjx
from mjinx.problem import Problem
from mjinx.components.tasks import ComTask, FrameTask, JointTask
from mjinx.solvers import LocalIKSolver, GlobalIKSolver
from mjinx.components.barriers import JointBarrier
import jax
from optax import adam

from mjinx.configuration import integrate

integrate_jit = jax.jit(integrate, static_argnames=["dt"])

# Initialize the robot model using MuJoCo
MJCF_PATH  = f"{file_absolute_parent}/assets/kbot/robot.mjcf"
mj_model = mj.MjModel.from_xml_path(MJCF_PATH)
mjx_model = mjx.put_model(mj_model)

print(f"Model nq (positions): {mjx_model.nq}")
print(f"Model nv (velocities): {mjx_model.nv}")
print(f"Expected: 10 arm joints")

# Print all joints that actually exist
print("\nActual joints in model:")
for i in range(mjx_model.njnt):
    joint_name = mj.mj_id2name(mj_model, mj.mjtObj.mjOBJ_JOINT, i)
    joint_type = mj_model.jnt_type[i]
    joint_qpos_adr = mj_model.jnt_qposadr[i]
    joint_dof_adr = mj_model.jnt_dofadr[i]
    
    type_names = {0: 'free', 1: 'ball', 2: 'slide', 3: 'hinge'}
    type_name = type_names.get(joint_type, f'unknown({joint_type})')
    
    print(f"Joint {i}: '{joint_name}' type={type_name} qpos_adr={joint_qpos_adr} dof_adr={joint_dof_adr}")


# Create instance of the problem
problem = Problem(mjx_model, v_min=np.concatenate([-1000*np.ones(5), np.zeros(5)]), v_max=np.concatenate([1000*np.ones(5), np.zeros(5)]))

# Add tasks to track desired behavior
frame_task = FrameTask("ee_task", cost=1, gain=20, obj_name="KB_C_501X_Right_Bayonet_Adapter_Hard_Stop",
                           mask=[1, 1, 1, 0, 0, 0, 0])  # position=[1,1,1], orientation=[0,0,0,0])

problem.add_component(frame_task)

joints_barrier = JointBarrier("jnt_range", gain=10, mask=np.array([*np.ones(5), *np.zeros(5)]))
problem.add_component(joints_barrier)

# Initialize the solver
local_solver = LocalIKSolver(mjx_model)
dt = 1e-1
# global_solver = GlobalIKSolver(mjx_model, adam(learning_rate=1), dt=1)

# Initializing initial condition

# Initialize solver data
q = np.zeros(10)
# solver_data = global_solver.init(q)
solver_data = local_solver.init()

# jit-compiling solve and integrate 

# global_solve_jit = jax.jit(global_solver.solve)
solve_jit = jax.jit(local_solver.solve)


# for _ in range(10):
#     frame_task.target_frame = np.array([*np.random.random(3), *np.eye(4)[0]])
    # _ = global_solve_jit(q, solver_data, problem.compile())

def jax_calculate_arm_joints(head_mat, left_wrist_mat, right_wrist_mat):
    global solver_data, q
    # Changing problem and compiling it
    quat = Rotation.from_matrix(right_wrist_mat[:3, :3]).as_quat(scalar_first=True)
    frame_task.target_frame = np.concatenate([right_wrist_mat[:3, 3], quat])
    problem_data = problem.compile()

    # Solving the instance of the problem
    opt_solution, solver_data = solve_jit(q, solver_data, problem_data)
    # q = opt_solution.q_opt  # Direct assignment for global IK

    q = integrate_jit(
            mjx_model,
            q,
            velocity=opt_solution.v_opt,
            dt=dt,
        )
    if np.any(np.isnan(q)):
        print("NaN detected in q")
        q = np.zeros(10)

    # print(opt_solution, q)

    return np.zeros(5), q[:5]
