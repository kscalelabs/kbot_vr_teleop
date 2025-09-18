import * as THREE from 'three';
import React from 'react';
import URDFLoader from 'urdf-loader';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js';
import { type trackingResult } from './webxrTracking';

// Fixed local Z-axis offset for STL models (-90 degrees)
const STL_Z_OFFSET = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), -Math.PI / 2);

export const actuatorMapping = {
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
  
export type sceneState = {
    scene: THREE.Scene | null;
    renderer: THREE.WebGLRenderer | null;
    leftHandMesh: THREE.Mesh | null;
    rightHandMesh: THREE.Mesh | null;
    videoPlaneMesh: THREE.Mesh | null;
    videoTexture: THREE.VideoTexture | null;
    statusPlaneMesh: THREE.Mesh | null;
    statusCanvas: HTMLCanvasElement | null;
    statusTexture: THREE.CanvasTexture | null;
    robot: any | null;
    pauseCommands: boolean;
    previousButtonStates: Map<string, boolean>;
  }
  
  export const DEFAULT_SCENE_STATE: sceneState = {
    scene: null,
    renderer: null,
    leftHandMesh: null,
    rightHandMesh: null,
    videoPlaneMesh: null,
    videoTexture: null,
    statusPlaneMesh: null,
    statusCanvas: null,
    statusTexture: null,
    robot: null,
    pauseCommands: false,
    previousButtonStates: new Map<string, boolean>()
  }
  
  export const cleanUpScene = (sceneState: sceneState) => {
    if (sceneState.scene) {
        // Remove all meshes
        const meshesToClean = [
          sceneState.leftHandMesh,
          sceneState.rightHandMesh,
          sceneState.videoPlaneMesh,
          sceneState.statusPlaneMesh,
          sceneState.robot
        ];

        meshesToClean.forEach(mesh => {
          if (mesh) {
            sceneState.scene!.remove(mesh);
            // Dispose of geometry and material if they exist
            if (mesh.geometry) {
              mesh.geometry.dispose();
            }
            if (mesh.material) {
              if (Array.isArray(mesh.material)) {
                mesh.material.forEach(material => material.dispose());
              } else {
                mesh.material.dispose();
              }
            }
          }
        });

        // Clean up textures
        if (sceneState.videoTexture) {
          sceneState.videoTexture.dispose();
        }
        if (sceneState.statusTexture) {
          sceneState.statusTexture.dispose();
        }
        sceneState = DEFAULT_SCENE_STATE;
      }
      
      // Clean up renderer
        if (sceneState.renderer) {
            sceneState.renderer.xr.enabled = false;
            sceneState.renderer.dispose();
          }
      }

  // Update STL mesh positions based on hand tracking
  export const updateSTLPositions = (sceneState: sceneState, trackingResult: trackingResult) => {
    if (!sceneState.scene) return;
    const handPositions = trackingResult.handPositions;
    const type = trackingResult.type;
    // Add meshes to scene if they exist but aren't added yet
    if (sceneState.leftHandMesh && !sceneState.scene.children.includes(sceneState.leftHandMesh)) {
      sceneState.scene.add(sceneState.leftHandMesh);
    }
    if (sceneState.rightHandMesh && !sceneState.scene.children.includes(sceneState.rightHandMesh)) {
      sceneState.scene.add(sceneState.rightHandMesh);
    }
    
    // Update left hand mesh
    if (handPositions.left && sceneState.leftHandMesh) {
      const position = handPositions.left.position;
      const orientation = handPositions.left.orientation;

      sceneState.leftHandMesh.position.set(position[0], position[1], position[2]);
      sceneState.leftHandMesh.quaternion.set(orientation[0], orientation[1], orientation[2], orientation[3]);
      // Apply persistent 90° rotation about the mesh's own Z axis
      if(type == "controller"){
        sceneState.leftHandMesh.quaternion.multiply(STL_Z_OFFSET);
      }
      sceneState.leftHandMesh.visible = true;
    } else if (sceneState.leftHandMesh) {
      sceneState.leftHandMesh.visible = false;
    }

    // Update right hand mesh
    if (handPositions.right && sceneState.rightHandMesh) {
      const position = handPositions.right.position;
      const orientation = handPositions.right.orientation;
      sceneState.rightHandMesh.position.set(position[0], position[1], position[2]);
      sceneState.rightHandMesh.quaternion.set(orientation[0], orientation[1], orientation[2], orientation[3]);
      // Apply persistent 90° rotation about the mesh's own Z axis
      if(type == "controller"){
        sceneState.rightHandMesh.quaternion.multiply(STL_Z_OFFSET);
      }
      sceneState.rightHandMesh.visible = true;
    } else if (sceneState.rightHandMesh) {
      sceneState.rightHandMesh.visible = false;
    }

    // Hide meshes if no hand positions
    if (!handPositions.left && !handPositions.right) {
      if (sceneState.leftHandMesh) sceneState.leftHandMesh.visible = false;
      if (sceneState.rightHandMesh) sceneState.rightHandMesh.visible = false;
    }
  };

  // Load STL models for hand tracking
  export const loadSTLModels = async (sceneState: sceneState) => {
    return new Promise((resolve, reject) => {
      const loader = new STLLoader();

      // Load STL file
      loader.load(
        '/prt0001.stl', // Path to STL file
        (geometry) => {
          // Create separate materials for each hand to avoid color sharing
          const leftMaterial = new THREE.MeshLambertMaterial({
            color: 0x888888, // Gray color
            side: THREE.DoubleSide
          });
          
          const rightMaterial = new THREE.MeshLambertMaterial({
            color: 0x888888, // Gray color
            side: THREE.DoubleSide
          });

          // Create left and right hand meshes with separate materials
          const leftMesh = new THREE.Mesh(geometry, leftMaterial);
          const rightMesh = new THREE.Mesh(geometry, rightMaterial);

          // Scale to make the largest dimension about 0.1 units (adjustable)
          const scale = 1

          // Apply scale and flip on all axes
          leftMesh.scale.set(scale, scale, -scale);
          rightMesh.scale.set(scale, scale, -scale);

          // Initially hide meshes
          leftMesh.visible = false;
          rightMesh.visible = false;

          sceneState.leftHandMesh = leftMesh;
          sceneState.rightHandMesh = rightMesh;

          // Add to scene if it exists
          if (sceneState.scene) {
            sceneState.scene.add(leftMesh);
            sceneState.scene.add(rightMesh);
            resolve(true);
          }
          reject(new Error('no scene ref for stl'));
        },
        (progress) => {
          // Progress callback
        },
        (error) => {
          console.error('Error loading STL:', error);
          reject(error);
        }
      );
    });
  };

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

  export const createStatusCanvas = (text: string) => {
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 128;
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;

    // Clear canvas with dark background
    ctx.fillStyle = '#333333';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Draw text
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 48px Arial';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, canvas.width / 2, canvas.height / 2);

    return canvas;
  };

  // Create video plane when stream and scene are ready
  export const createVideoPlane = async (sceneState: sceneState, stream: MediaStream | null, videoRef: React.RefObject<HTMLVideoElement>) => {
    return new Promise((resolve, reject) => {
      if (sceneState.scene) {
        // Create video texture if stream is available
        let videoTexture = null;
        if (stream && videoRef.current) {
          // Wait for video to be ready before creating texture
          const setupVideoTexture = () => {
            if (videoRef.current && videoRef.current.readyState >= 2) {
              videoTexture = new THREE.VideoTexture(videoRef.current);
              videoTexture.minFilter = THREE.LinearFilter;
              videoTexture.magFilter = THREE.LinearFilter;
              sceneState.videoTexture = videoTexture;
              createPlaneWithTexture();
            } else {
              // Wait for video to be ready
              setTimeout(setupVideoTexture, 100);
            }
          };
          
          const createPlaneWithTexture = () => {
            createVideoPlaneMesh(videoTexture);
            resolve(true);
          };
          
          setupVideoTexture();
          return;
        } else {
          // No stream, create plane with orange fallback
          createVideoPlaneMesh(null);
          resolve(true);
          return;
        }
        
        function createVideoPlaneMesh(videoTexture: THREE.VideoTexture | null) {
          // Create video plane geometry matching video aspect ratio (1280x1080)
          const videoAspectRatio = 1280 / 1080; // 1.185
          const height = 3.0;
          const width = height * videoAspectRatio; // Maintain video aspect ratio
          const segments = 256;
          const planeGeometry = new THREE.PlaneGeometry(width, height, segments, segments);

          // Create material - use video texture if available, otherwise orange
          const planeMaterial = new THREE.MeshBasicMaterial({
            map: videoTexture || null,
            color: videoTexture ? 0xffffff : 0xff8c00, // Orange if no video
            side: THREE.DoubleSide
          });

          // Create mesh and position it directly in front of camera
          const videoPlaneMesh = new THREE.Mesh(planeGeometry, planeMaterial);
          videoPlaneMesh.position.set(0, 0, -2); // Position in front of user

          sceneState.videoPlaneMesh = videoPlaneMesh;
          sceneState.scene.add(videoPlaneMesh);

          // Create status plane beneath the video plane
          const videoHeight = 2.0;
          const videoWidth = videoHeight * videoAspectRatio;

          // Status plane: same width, 1/6th height
          const statusHeight = videoHeight / 6;
          const statusWidth = videoWidth;
          const statusGeometry = new THREE.PlaneGeometry(statusWidth, statusHeight);

          // Create initial status canvas
          const initialCanvas = createStatusCanvas('false');
          if (initialCanvas) {
            sceneState.statusCanvas = initialCanvas;
            const statusTexture = new THREE.CanvasTexture(initialCanvas);
            sceneState.statusTexture = statusTexture;

            const statusMaterial = new THREE.MeshBasicMaterial({
              map: statusTexture,
              side: THREE.DoubleSide
            });

            const statusPlaneMesh = new THREE.Mesh(statusGeometry, statusMaterial);

            // Position beneath video plane and angle slightly up
            statusPlaneMesh.position.set(0, -videoHeight / 2 - statusHeight / 2 - 0.1, -2);
            statusPlaneMesh.rotation.x = -Math.PI / 12; // 15 degrees up (negative for upward angle)

            sceneState.statusPlaneMesh = statusPlaneMesh;
            sceneState.scene.add(statusPlaneMesh);
          }
        }
      }
      else {
        reject(new Error('no scene ref for createVideoPlane'));
      }
    });
  };

  // Update video texture when stream becomes available
  export const updateVideoTexture = (sceneState: sceneState, stream: MediaStream | null, videoRef: React.RefObject<HTMLVideoElement>) => {
    if (stream && videoRef.current && sceneState.videoPlaneMesh && sceneState.videoPlaneMesh.material instanceof THREE.MeshBasicMaterial) {
      // Wait for video to be ready
      const setupVideoTexture = () => {
        if (videoRef.current && videoRef.current.readyState >= 2) {
          const videoTexture = new THREE.VideoTexture(videoRef.current);
          videoTexture.minFilter = THREE.LinearFilter;
          videoTexture.magFilter = THREE.LinearFilter;
          
          sceneState.videoTexture = videoTexture;
          const material = sceneState.videoPlaneMesh!.material as THREE.MeshBasicMaterial;
          material.map = videoTexture;
          material.color.setHex(0xffffff); // White when video is available
          material.needsUpdate = true;
          
          console.log('Video texture updated successfully');
        } else {
          // Wait for video to be ready
          setTimeout(setupVideoTexture, 100);
        }
      };
      
      setupVideoTexture();
    }
  };