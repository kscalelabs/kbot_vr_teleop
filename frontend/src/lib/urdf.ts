import URDFLoader from 'urdf-loader';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js';
import { type sceneState } from './three-scene';
import * as THREE from 'three';

const actuatorMapping = {
    "left": {
      "0": "dof_left_shoulder_pitch_03",
      "1": "dof_left_shoulder_roll_03",
      "2": "dof_left_shoulder_yaw_02",
      "3": "dof_left_elbow_02",
      "4": "dof_left_wrist_00"
    },
    "right": {
      "0": "dof_right_shoulder_pitch_03",
      "1": "dof_right_shoulder_roll_03",
      "2": "dof_right_shoulder_yaw_02",
      "3": "dof_right_elbow_02",
      "4": "dof_right_wrist_00"
    }
  }

// Load URDF robot after scene is initialized
export const loadURDFRobot = async (sceneState: sceneState, updateStatus: (msg: string) => void) => {
    return new Promise((resolve, reject) => {
        if (sceneState.scene) {
            const loader = new URDFLoader();

            // Set up STL loader for mesh loading (same as urdf-viewer)
            loader.loadMeshCb = (path, manager, done) => {
                new STLLoader(manager).load(path, (geometry) => {
                    const material = new THREE.MeshPhongMaterial({ color: 0x888888 });
                    const mesh = new THREE.Mesh(geometry, material);
                    done(mesh);
                });
            };

            loader.load(
                '/robot.urdf',
                (robot) => {
                    sceneState.robot = robot;

                    // Scale the robot to a reasonable size
                    robot.scale.setScalar(1);

                    // Position the robot in front of the camera
                    robot.position.set(0, -0.239, 0);

                    // Rotate robot 90 degrees around X-axis to point straight up
                    robot.rotation.x = Math.PI / -2; // 90 degrees in radians
                    robot.rotation.z = Math.PI / 2;
                    // Make robot visible
                    robot.visible = true;

                    sceneState.scene.add(robot);

                    resolve(true);
                },
                (progress) => {
                    // Progress callback
                },
                (error) => {
                    updateStatus('Error loading URDF');
                    console.error('Error loading URDF:', error);
                    reject(error);
                }
            );
        }
        else {
            updateStatus('no scene ref');
            reject(new Error('no scene ref'));
        }
    });
};

export const updateURDF = (side: string, jointArray: number[], sceneState: sceneState) => {
    if (!actuatorMapping[side]) {
      return;
    }

    if (!sceneState.robot) {
      return;
    }

    const jointUpdates: { [key: string]: number } = {};

    jointArray.forEach((angleInRadians, index) => {
      const jointName = actuatorMapping[side][index.toString()];
      if (jointName && sceneState.robot?.joints[jointName]) {
        // Store update for batch processing
        jointUpdates[jointName] = angleInRadians;

        // Update robot joint immediately
        sceneState.robot.joints[jointName].setJointValue(angleInRadians);
      }
    });
  };