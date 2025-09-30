import * as THREE from 'three';
  
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
    lastLeftColorRef: number;
    lastRightColorRef: number;
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
    pauseCommands: true,
    previousButtonStates: new Map<string, boolean>(),
    lastLeftColorRef: -1,
    lastRightColorRef: -1
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
          // Create video plane geometry that matches the actual video aspect ratio
          const defaultVideoWidth = 1920;  // fallback to expected stream size
          const defaultVideoHeight = 1080;  // fallback to expected stream size
          const actualVideoWidth = (videoRef.current && (videoRef.current as HTMLVideoElement).videoWidth) || defaultVideoWidth;
          const actualVideoHeight = (videoRef.current && (videoRef.current as HTMLVideoElement).videoHeight) || defaultVideoHeight;
          const videoAspectRatio = actualVideoWidth / actualVideoHeight;

          const videoHeight = 3.0;
          const videoWidth = videoHeight * videoAspectRatio; // Maintain video aspect ratio
          const segments = 256;
          const planeGeometry = new THREE.PlaneGeometry(videoWidth, videoHeight, segments, segments);

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

          // Create status plane beneath the video plane (use same computed width/height)

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

  // Function to get color based on distance (green to red spectrum for both hands)
  export const getDistanceColor = (distance: number): number => {
    // Clamp distance between 0 and 0.2 for color interpolation
    const clampedDistance = Math.min(Math.max(distance, 0), 0.2);
    
    // Scale distance to 0-1 range for interpolation
    const scaledDistance = clampedDistance / 0.2;
    
    // Interpolate from green (0x00ff00) to red (0xff0000)
    const red = Math.floor(scaledDistance * 255);
    const green = Math.floor((1 - scaledDistance) * 255);
    
    return (red << 16) | (green << 8) | 0; // RGB format
  };

  // Function to update STL mesh color based on distance
  export const updateMeshColor = (mesh: THREE.Mesh | null, color: number, handSide: string, lastColorRef: number, sceneState: sceneState) => {
    if (mesh && mesh.material instanceof THREE.MeshLambertMaterial) {
      if (lastColorRef !== color) {
        mesh.material.color.setHex(color);
        if (handSide === 'LEFT') {
          sceneState.lastLeftColorRef = color;
        } else if (handSide === 'RIGHT') {
          sceneState.lastRightColorRef = color;
        }
      }
    }
  };