import { useRef, useState, useEffect } from 'react';
import * as THREE from 'three';
import URDFLoader from 'urdf-loader';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js';
import { handleTracking, handleControllerInput, type localTargetLocation } from './webxrTracking';
import { sceneState, DEFAULT_SCENE_STATE, cleanUpScene, updateSTLPositions, 
  createStatusCanvas, createVideoPlane, updateVideoTexture, loadSTLModels, loadURDFRobot, actuatorMapping } from './sceneHandling';

interface VRViewerProps {
  stream: MediaStream | null;
  url: string;
  udpHost: string;
}

export default function VRViewer({ stream, url, udpHost }: VRViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const lastHandSendRef = useRef<number>(0);
  const [status, setStatus] = useState('');
  const wsRef = useRef<WebSocket | null>(null);
  const [loadCount, setLoadCount] = useState(0);
  
  // Track last color updates to prevent flickering
  const lastLeftColorRef = useRef<number>(-1);
  const lastRightColorRef = useRef<number>(-1);

  const xrSessionRef = useRef<XRSession | null>(null);

  // Single state object for all scene-related refs
  const sceneStateRef = useRef<sceneState>(DEFAULT_SCENE_STATE);

  useEffect(() => {
    // Use the first available stream for the billboard
    if (videoRef.current && stream) {
      videoRef.current.srcObject = stream;
      videoRef.current.play().catch(e => console.log(`Video play warning: ${e.message}`));
      
      // Update video texture if plane already exists
      if (sceneStateRef.current.videoPlaneMesh) {
        updateVideoTexture(sceneStateRef.current, stream, videoRef);
      }
    }
  }, [stream]);

  useEffect(() => {

    const initializeVR = async () => {
      await resetScene();
      startVR();
    };

    initializeVR();

    return () => {
      resetScene()
    };
  }, []);

  // Update status text when pause state changes
  useEffect(() => {
    if (sceneStateRef.current.statusCanvas && sceneStateRef.current.statusTexture) {
      const newCanvas = createStatusCanvas(sceneStateRef.current.pauseCommands.toString());
      if (newCanvas) {
        sceneStateRef.current.statusCanvas = newCanvas;
        sceneStateRef.current.statusTexture.image = newCanvas;
        sceneStateRef.current.statusTexture.needsUpdate = true;
      }
    }
  }, [sceneStateRef.current.pauseCommands]);

  const resetScene = async () => {
    if (xrSessionRef.current) {
      await xrSessionRef.current.end().catch(err => {
        console.warn('Error ending XR session:', err);
      });
      xrSessionRef.current = null;
    }

    // Close WebSocket if open
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    // Clean up Three.js objects (synchronous)
    cleanUpScene(sceneStateRef.current);

    // Clean up video element
    if (videoRef.current) {
      videoRef.current.pause();
      videoRef.current.srcObject = null;
    }
  }


  // Initialize Three.js scene
  const initThreeScene = async () => {
    return new Promise((resolve, reject) => {
      try {
        const scene = new THREE.Scene();

        // Set a background color
        scene.background = new THREE.Color(0x222222);

        // Add basic lighting
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.8);
        scene.add(ambientLight);

        sceneStateRef.current.scene = scene;
        resolve(true);
      }
      catch (error) {
        updateStatus('Error initializing Three.js scene');
        reject(new Error('no scene ref for initThreeScene'));
      }
    });
  };

  // Function to get color based on distance (green to red spectrum for both hands)
  const getDistanceColor = (distance: number): number => {
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
  const updateMeshColor = (mesh: THREE.Mesh | null, color: number, handSide: string, lastColorRef: React.MutableRefObject<number>) => {
    if (mesh && mesh.material instanceof THREE.MeshLambertMaterial) {
      if (lastColorRef.current !== color) {
        mesh.material.color.setHex(color);
        lastColorRef.current = color;
      }
    }
  };

  const processJointArray = (side: string, jointArray: number[]) => {
    if (!actuatorMapping[side]) {
      console.error(`No mapping found for side: ${side}`);
      return;
    }

    if (!sceneStateRef.current.robot) {
      console.warn('Robot not loaded yet');
      return;
    }

    const jointUpdates: { [key: string]: number } = {};

    jointArray.forEach((angleInRadians, index) => {
      const jointName = actuatorMapping[side][index.toString()];
      if (jointName && sceneStateRef.current.robot?.joints[jointName]) {
        // Store update for batch processing
        jointUpdates[jointName] = angleInRadians;

        // Update robot joint immediately
        sceneStateRef.current.robot.joints[jointName].setJointValue(angleInRadians);
      } else {
        console.warn(`Joint not found for ${side}[${index}]: ${jointName}`);
      }
    });

    console.log(`Updated ${Object.keys(jointUpdates).length} joints for ${side} arm`);
  };

  const updateStatus = (msg: string) => {
    setStatus(msg);
  };

  const startVR = async () => {
    // Prevent multiple sessions from starting
    if (xrSessionRef.current) {
      return;
    }

    updateStatus('Starting VR URDF Viewer...');
    const canvas = canvasRef.current;
    if (!canvas) return;

    // Create Three renderer and enable XR
    const renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: true,
    });

    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.xr.enabled = true;

    // Tell Three which reference space to use internally
    renderer.xr.setReferenceSpaceType('local');

    sceneStateRef.current.renderer = renderer;
    setLoadCount(0);
    updateStatus('Creating Three.js Dcene');
    await initThreeScene();
    setLoadCount(1);
    updateStatus('Creating Video Plane');
    await createVideoPlane(sceneStateRef.current, stream, videoRef);
    setLoadCount(2);
    updateStatus('Loading STL Models');
    await loadSTLModels(sceneStateRef.current);
    setLoadCount(3);
    updateStatus('Loading Robot URDF');
    await loadURDFRobot(sceneStateRef.current, updateStatus);
    setLoadCount(4);
    updateStatus('Setting up Tracking WebSocket');
    await setupTrackingWebSocket()
    setLoadCount(5);
    updateStatus('Requesting VR Session');

    // Request the XR session with appropriate features
    try {
      const session = await navigator.xr.requestSession('immersive-vr', {
        requiredFeatures: ['local-floor', 'viewer', 'hand-tracking'],
        optionalFeatures: ['layers'],
      });
      xrSessionRef.current = session;
      // Hand the session to Three (this sets up XRWebGLLayer, etc.)
      setLoadCount(6);
      await renderer.xr.setSession(session);
      updateStatus('XR Session Running ');
    }
    catch (err) {
      setLoadCount(6);
      updateStatus('XR Session Running ');
      return
    }
    // Get the reference space from Three (do NOT call session.requestReferenceSpace)
    const refSpace = renderer.xr.getReferenceSpace();

    // Setup WebXR session event listeners for camera positioning
    renderer.xr.addEventListener('sessionstart', () => {
      // Position the VR camera at the desired location
      const vrCamera = renderer.xr.getCamera();
      vrCamera.position.set(0.107, 0.239, -5.000);
      vrCamera.lookAt(1, 0.239, -2.000); // Face towards positive X
      updateStatus('VR camera positioned');
    });

    renderer.xr.addEventListener('sessionend', () => {
      updateStatus('VR Session Ended');
    });

    // Create a stable camera (Three will substitute XR camera internally)
    const camera = new THREE.PerspectiveCamera(
      75, // Field of view
      window.innerWidth / window.innerHeight, // Aspect ratio
      0.1, // Near plane
      100  // Far plane
    );

    // Use Three's XR render loop to obtain XRFrame
    renderer.setAnimationLoop((time, frame) => {
      if (!frame || !sceneStateRef.current.scene) return;

      // Handle controller input for pause toggle
      handleControllerInput(frame, refSpace, sceneStateRef.current);

      // Tracking → positions/orientations → STL mesh updates
      let handPositions = handleTracking(frame, refSpace, wsRef, lastHandSendRef, sceneStateRef.current.pauseCommands);
      if (handPositions) updateSTLPositions(sceneStateRef.current, handPositions);

      renderer.render(sceneStateRef.current.scene, camera);
    });
  };

  const setupTrackingWebSocket = async () => {
    return new Promise((resolve, reject) => {
      try {
        let webSocket = new WebSocket(url);

        webSocket.onopen = () => {
          webSocket.send(JSON.stringify({
            role: "teleop",
            udp_host: udpHost,
          }));
          wsRef.current = webSocket;
          updateStatus('Hand tracking WebSocket connected');
          resolve(true);
        };

        webSocket.onmessage = (event) => {
          const data = JSON.parse(event.data);
          if (data.type === "kinematics") {
            // Process left and right joint arrays
            if(data.joints) {
              if (data.joints.left && Array.isArray(data.joints.left)) {
                processJointArray('left', data.joints.left);
              }

              if (data.joints.right && Array.isArray(data.joints.right)) {
                processJointArray('right', data.joints.right);
              }
            }
            
            // Process distance data for STL mesh color updates
            if(data.distances) {
              console.log(`Received distances - Left: ${data.distances.left?.toFixed(3)}, Right: ${data.distances.right?.toFixed(3)}`);
              
              // Update left hand mesh color based on its own distance (green to red spectrum)
              if (data.distances.left !== undefined && sceneStateRef.current.leftHandMesh) {
                const leftDistance = data.distances.left;
                const leftColor = getDistanceColor(leftDistance);
                updateMeshColor(sceneStateRef.current.leftHandMesh, leftColor, 'LEFT', lastLeftColorRef);
              }
              
              // Update right hand mesh color based on its own distance (green to red spectrum)
              if (data.distances.right !== undefined && sceneStateRef.current.rightHandMesh) {
                const rightDistance = data.distances.right;
                const rightColor = getDistanceColor(rightDistance);
                updateMeshColor(sceneStateRef.current.rightHandMesh, rightColor, 'RIGHT', lastRightColorRef);
              }
            }
          }
        };

        webSocket.onerror = (error) => {
          resolve(false);
          console.log(`Hand tracking WebSocket error: ${error}`);
          updateStatus('Hand tracking WebSocket error');
        };

        webSocket.onclose = () => {
          console.log('Hand tracking WebSocket closed');
          updateStatus('Hand tracking WebSocket closed');
        };

      } catch (error) {
        console.log(`Failed to setup hand tracking WebSocket: ${error}`);
        updateStatus('Failed to setup hand tracking WebSocket');
      }
    });
  };

  const createWebLoadingWheel = (progress: number) => {
    const canvas = document.createElement('canvas');
    canvas.width = 200;
    canvas.height = 200;
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;

    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const radius = 80;
    const lineWidth = 15;

    // Draw background circle
    ctx.strokeStyle = '#333333';
    ctx.lineWidth = lineWidth;
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, 2 * Math.PI);
    ctx.stroke();

    // Draw progress arc
    ctx.strokeStyle = '#ff8c00';
    ctx.lineWidth = lineWidth;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, -Math.PI / 2, -Math.PI / 2 + (2 * Math.PI * progress));
    ctx.stroke();

    // Draw progress text
    ctx.fillStyle = '#ff8c00';
    ctx.font = 'bold 30px Arial';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(`${Math.round(progress * 100)}%`, centerX, centerY);

    return canvas.toDataURL();
  };

  return (
    <div style={{
      padding: '0',
      margin: '0',
      fontFamily: 'Arial, sans-serif',
      backgroundColor: '#000000',
      color: '#ff8c00',
      height: '100%',
      width: '100vw',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      overflow: 'hidden'
    }}>

      {status && (
        <div style={{
          marginBottom: '20px',
          padding: '15px',
          backgroundColor: '#000000',
          border: '2px solid #ff8c00',
          borderRadius: '8px',
          fontSize: '32px',
          fontWeight: 'bold',
          textAlign: 'center',
          minWidth: '300px'
        }}>
          {status}
        </div>
      )}

      {/* Loading wheel */}
      {loadCount < 7 && (
        <div style={{
          marginBottom: '20px',
          backgroundImage: `url(${createWebLoadingWheel(loadCount / 6)})`,
          backgroundSize: 'contain',
          backgroundRepeat: 'no-repeat',
          backgroundPosition: 'center',
          width: '150px',
          height: '150px'
        }} />
      )}
      <video
        ref={videoRef}
        style={{ display: 'none' }}
        muted
        playsInline
        autoPlay
      />

      <canvas ref={canvasRef} style={{ display: 'none' }} />
    </div>
  );
}

