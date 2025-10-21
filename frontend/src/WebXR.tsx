import { useRef, useState, useEffect } from 'react';
import * as THREE from 'three';
import { handleTracking, handleControllerInput} from './lib/tracking';
import { cleanUpScene, 
  createStatusCanvas, createVideoPlane, updateVideoTexture, 
  getDistanceColor, updateMeshColor, initThreeScene } from './lib/three-scene';
import { loadURDFRobot, updateURDF } from './lib/urdf';
import { updateSTLPositions, loadSTLModelsWithFallback } from './lib/stl';
import { SceneState, DEFAULT_SCENE_STATE, ForwardKinematicsMessage } from './lib/types';

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
  const [leftJoystick, setLeftJoystick] = useState([0, 0]);
  const [rightJoystick, setRightJoystick] = useState([0, 0]);
  const xrSessionRef = useRef<XRSession | null>(null);
  const [joystickScale, setJoystickScale] = useState(0.1);
  const [pauseCommands, setPauseCommands] = useState(true);
  
  // Single state object for all scene-related refs
  const sceneStateRef = useRef<SceneState>(DEFAULT_SCENE_STATE);

  useEffect(() => {
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

  // Update status text when joystick state changes
  useEffect(() => {
    if (sceneStateRef.current.statusCanvas && sceneStateRef.current.statusTexture) {
      const joystickText = `Left: (${leftJoystick[0].toFixed(2)}, ${leftJoystick[1].toFixed(2)})\nRight: (${rightJoystick[0].toFixed(2)}, ${rightJoystick[1].toFixed(2)})\nScale: ${joystickScale.toFixed(2)}`;
      const newCanvas = createStatusCanvas(joystickText, pauseCommands);
      if (newCanvas) {
        sceneStateRef.current.statusCanvas = newCanvas;
        sceneStateRef.current.statusTexture.image = newCanvas;
        sceneStateRef.current.statusTexture.needsUpdate = true;
      }
    }
  }, [leftJoystick, rightJoystick, joystickScale, pauseCommands]);

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

  const startVR = async () => {
    // Prevent multiple sessions from starting
    if (xrSessionRef.current) {
      return;
    }

    setStatus('Starting VR URDF Viewer...');
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
    setStatus('Creating Three.js Dcene');
    try{
      initThreeScene(sceneStateRef.current);
      throw new Error('Failed to create Three.js scene');
    }
    catch (error) {
      setStatus('Error initializing Three.js scene');
    }
    setLoadCount(progress => progress + 1);
    setStatus('Creating Video Plane');
    await createVideoPlane(sceneStateRef.current, stream, videoRef);
    setLoadCount(progress => progress + 1);
    setStatus('Loading STL Models');
    await loadSTLModelsWithFallback(sceneStateRef.current);
    setLoadCount(progress => progress + 1);
    setStatus('Loading Robot URDF');
    await loadURDFRobot(sceneStateRef.current, setStatus);
    setLoadCount(progress => progress + 1);
    setStatus('Setting up Tracking WebSocket');
    await setupTrackingWebSocket()
    setLoadCount(progress => progress + 1);
    setStatus('Requesting VR Session');

    // Request the XR session with appropriate features
    try {
      const session = await navigator.xr.requestSession('immersive-vr', {
        requiredFeatures: ['local-floor', 'viewer'],
        optionalFeatures: ['layers', 'hand-tracking'],
      });
      xrSessionRef.current = session;
      // Hand the session to Three (this sets up XRWebGLLayer, etc.)
      setLoadCount(6);
      await renderer.xr.setSession(session);
      setStatus('XR Session Running ');
    }
    catch (err) {
      setLoadCount(6);
      setStatus('XR Session Running ');
      return
    }
    // Get the reference space from Three (do NOT call session.requestReferenceSpace)
    const refSpace = renderer.xr.getReferenceSpace();

    // Setup WebXR session event listeners for camera positioning
    renderer.xr.addEventListener('sessionstart', async () => {
      // Position the VR camera at the desired location
      const vrCamera = renderer.xr.getCamera();
      vrCamera.position.set(0.107, 0.239, -5.000);
      vrCamera.lookAt(1, 0.239, -2.000); // Face towards positive X
      await new Promise(resolve => setTimeout(resolve, 2000)); 
      setStatus('VR camera positioned');
    });

    renderer.xr.addEventListener('sessionend', () => {
      setStatus('VR Session Ended');
    });

    // Create a stable camera (Three will substitute XR camera internally)
    const camera = new THREE.PerspectiveCamera(
      75, // Field of view
      window.innerWidth / window.innerHeight, // Aspect ratio
      0.1, // Near plane
      100  // Far plane
    );

    renderer.setAnimationLoop((time, frame) => {
      if (!frame || !sceneStateRef.current.scene) return;

      // Handle controller input for pause toggle and joystick scale
      handleControllerInput(frame, refSpace, sceneStateRef.current);

      // Tracking → positions/orientations → STL mesh updates
      let trackingData = handleTracking(frame, refSpace, wsRef, lastHandSendRef, sceneStateRef.current.pauseCommands, sceneStateRef.current.joystickScale);
      if (trackingData) {
        updateSTLPositions(sceneStateRef.current, trackingData);
        // Update joystick states if controller data is available
        if (trackingData.type === "controller") {
          if (trackingData.left) {
            setLeftJoystick([trackingData.left.joystickX || 0, trackingData.left.joystickY || 0]);
          }
          if (trackingData.right) {
            setRightJoystick([trackingData.right.joystickX || 0, trackingData.right.joystickY || 0]);
          }
          // Update scale and pause states for display
          setJoystickScale(sceneStateRef.current.joystickScale);
          setPauseCommands(sceneStateRef.current.pauseCommands);
        }
      }
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
            robot_ip: udpHost,
          }));
          wsRef.current = webSocket;
          setStatus('Hand tracking WebSocket connected');
          resolve(true);
        };

        webSocket.onmessage = (event) => {
          const data: ForwardKinematicsMessage= JSON.parse(event.data);
          if (data.type === "kinematics") {
            // Process left and right joint arrays
            if(data.joints) {
              if (data.joints.left && Array.isArray(data.joints.left)) {
                updateURDF('left', data.joints.left, sceneStateRef.current);
              }

              if (data.joints.right && Array.isArray(data.joints.right)) {
                updateURDF('right', data.joints.right, sceneStateRef.current);
              }
            }
            
            // Process distance data for STL mesh color updates
            if(data.distances) {              
              // Update left hand mesh color based on its own distance (green to red spectrum)
              if (data.distances.left !== undefined && sceneStateRef.current.leftHandMesh) {
                const leftDistance = data.distances.left;
                const leftColor = getDistanceColor(leftDistance);
                updateMeshColor(sceneStateRef.current.leftHandMesh, leftColor, 'LEFT', sceneStateRef.current.lastLeftColorRef, sceneStateRef.current);
              }
              
              // Update right hand mesh color based on its own distance (green to red spectrum)
              if (data.distances.right !== undefined && sceneStateRef.current.rightHandMesh) {
                const rightDistance = data.distances.right;
                const rightColor = getDistanceColor(rightDistance);
                updateMeshColor(sceneStateRef.current.rightHandMesh, rightColor, 'RIGHT', sceneStateRef.current.lastRightColorRef, sceneStateRef.current);
              }
            }
          }
        };

        webSocket.onerror = (error) => {
          resolve(false);
          setStatus('Hand tracking WebSocket error');
        };

        webSocket.onclose = () => {
          setStatus('Hand tracking WebSocket closed');
        };

      } catch (error) {
        setStatus('Failed to setup hand tracking WebSocket');
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

