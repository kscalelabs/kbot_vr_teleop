import React, { useRef, useState, useEffect } from 'react';
import * as THREE from 'three';
import URDFLoader from 'urdf-loader';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js';
import { handleHandTracking, handleControllerTracking } from './webxrTracking';

interface URDFViewerProps {
  stream: MediaStream | null;
  url: string;
  hands: boolean;
}

export default function URDFViewer({ stream, url, hands }: URDFViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const lastHandSendRef = useRef<number>(0);
  const [started, setStarted] = useState(false);
  const [status, setStatus] = useState('');
  const wsRef = useRef<WebSocket | null>(null);
  const threeSceneRef = useRef<THREE.Scene|null>(null);
  const threeRendererRef = useRef<THREE.WebGLRenderer|null>(null);
  const leftHandMeshRef = useRef<THREE.Mesh|null>(null);
  const rightHandMeshRef = useRef<THREE.Mesh|null>(null);
  const leftSphereRef = useRef<THREE.Mesh|null>(null);
  const rightSphereRef = useRef<THREE.Mesh|null>(null);
  const videoPlaneMeshRef = useRef<THREE.Mesh|null>(null);
  const videoTextureRef = useRef<THREE.VideoTexture|null>(null);
  const statusPlaneMeshRef = useRef<THREE.Mesh|null>(null);
  const statusCanvasRef = useRef<HTMLCanvasElement|null>(null);
  const statusTextureRef = useRef<THREE.CanvasTexture|null>(null);
  const [videoPlaneReady, setVideoPlaneReady] = useState(false);
  const [ready, setReady] = useState(false);
  const robotRef = useRef<any>(null);
  const [wsMapData, setWsMapData] = useState<any>(null);
  const [mapData, setMapData] = useState<any>(null);
  const redSphereRef = useRef<THREE.Mesh|null>(null);
  const pauseCommandsRef = useRef<boolean>(false);
  const previousButtonStatesRef = useRef<Map<string, boolean>>(new Map());
  
  useEffect(() => {
    // Use the first available stream for the billboard
    if (videoRef.current && stream) {
      videoRef.current.srcObject = stream;
      videoRef.current.play().catch(e => console.log(`Video play warning: ${e.message}`));
    }
  }, [stream]);

  // Create status text canvas
  const createStatusCanvas = (text: string) => {
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
  useEffect(() => {
    if (threeSceneRef.current && !videoPlaneMeshRef.current) {
      // Create video texture if stream is available
      let videoTexture = null;
      if (stream && videoRef.current) {
        videoTexture = new THREE.VideoTexture(videoRef.current);
        videoTexture.minFilter = THREE.LinearFilter;
        videoTexture.magFilter = THREE.LinearFilter;
        videoTextureRef.current = videoTexture;
      }

      // Create video plane geometry matching video aspect ratio (1280x1080)
      const videoAspectRatio = 1280 / 1080; // 1.185
      const height = 2.0;
      const width = height * videoAspectRatio; // Maintain video aspect ratio
      const segments = 32;
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
      
      videoPlaneMeshRef.current = videoPlaneMesh;
      threeSceneRef.current.add(videoPlaneMesh);

      // Create status plane beneath the video plane
      if (!statusPlaneMeshRef.current) {
        const videoAspectRatio = 1280 / 1080; // 1.185
        const videoHeight = 2.0;
        const videoWidth = videoHeight * videoAspectRatio;
        
        // Status plane: same width, 1/6th height
        const statusHeight = videoHeight / 6;
        const statusWidth = videoWidth;
        const statusGeometry = new THREE.PlaneGeometry(statusWidth, statusHeight);
        
        // Create initial status canvas
        const initialCanvas = createStatusCanvas('false');
        if (initialCanvas) {
          statusCanvasRef.current = initialCanvas;
          const statusTexture = new THREE.CanvasTexture(initialCanvas);
          statusTextureRef.current = statusTexture;
          
          const statusMaterial = new THREE.MeshBasicMaterial({ 
            map: statusTexture,
            side: THREE.DoubleSide
          });
          
          const statusPlaneMesh = new THREE.Mesh(statusGeometry, statusMaterial);
          
          // Position beneath video plane and angle slightly up
          statusPlaneMesh.position.set(0, -videoHeight/2 - statusHeight/2 - 0.1, -2);
          statusPlaneMesh.rotation.x = -Math.PI / 12; // 15 degrees up (negative for upward angle)
          
          statusPlaneMeshRef.current = statusPlaneMesh;
          threeSceneRef.current.add(statusPlaneMesh);
        }
      }
      
      setVideoPlaneReady(true);
    }
  }, [stream, threeSceneRef.current]);

  // Update status text when pause state changes
  useEffect(() => {
    if (statusCanvasRef.current && statusTextureRef.current) {
      const newCanvas = createStatusCanvas(pauseCommandsRef.current.toString());
      if (newCanvas) {
        statusCanvasRef.current = newCanvas;
        statusTextureRef.current.image = newCanvas;
        statusTextureRef.current.needsUpdate = true;
      }
    }
  }, [pauseCommandsRef.current]);

  // Load joint mapping data
  useEffect(() => {
    const loadMappingData = async () => {
      try {
        const wsMapResponse = await fetch('/wsmap.json');
        const wsMap = await wsMapResponse.json();
        setWsMapData(wsMap);
        
        const mapResponse = await fetch('/map.json');
        const map = await mapResponse.json();
        setMapData(map);
      } catch (error) {
        console.error('Error loading mapping data:', error);
      }
    };
    
    loadMappingData();
  }, []);

  // Load STL models when component mounts
  useEffect(() => {
    const loader = new STLLoader();
    
    // Load STL file
    loader.load(
      '/prt0001.stl', // Path to STL file
      (geometry) => {
        // Create material that responds to ambient light
        const material = new THREE.MeshLambertMaterial({ 
          color: 0x888888, // Gray color
          side: THREE.DoubleSide 
        });

        // Create left and right hand meshes from the same geometry
        const leftMesh = new THREE.Mesh(geometry, material);
        const rightMesh = new THREE.Mesh(geometry, material);

        // Calculate appropriate scale based on STL bounding box
        geometry.computeBoundingBox();
        const boundingBox = geometry.boundingBox!;
        const size = boundingBox.max.clone().sub(boundingBox.min);
        const maxDimension = Math.max(size.x, size.y, size.z);
        
        // Scale to make the largest dimension about 0.1 units (adjustable)
        const scale = 1
        
        // Apply scale and flip on all axes
        leftMesh.scale.set(scale, scale, -scale);
        rightMesh.scale.set(scale, scale, -scale);

        // Initially hide meshes
        leftMesh.visible = false;
        rightMesh.visible = false;

        leftHandMeshRef.current = leftMesh;
        rightHandMeshRef.current = rightMesh;

        // Add to scene if it exists
        if (threeSceneRef.current) {
          threeSceneRef.current.add(leftMesh);
          threeSceneRef.current.add(rightMesh);
        }
      },
      (progress) => {
        // Progress callback
      },
      (error) => {
        console.error('Error loading STL:', error);
        // Fallback to cubes if STL fails
        createFallbackCubes();
      }
    );

    // Clean up meshes when component unmounts
    return () => {
      if (leftHandMeshRef.current && threeSceneRef.current) {
        threeSceneRef.current.remove(leftHandMeshRef.current);
        leftHandMeshRef.current = null;
      }
      if (rightHandMeshRef.current && threeSceneRef.current) {
        threeSceneRef.current.remove(rightHandMeshRef.current);
        rightHandMeshRef.current = null;
      }
      if (leftSphereRef.current && threeSceneRef.current) {
        threeSceneRef.current.remove(leftSphereRef.current);
        leftSphereRef.current = null;
      }
      if (rightSphereRef.current && threeSceneRef.current) {
        threeSceneRef.current.remove(rightSphereRef.current);
        rightSphereRef.current = null;
      }
    };
  }, []);

  // Fallback function to create cubes if STL loading fails
  const createFallbackCubes = () => {
    if (threeSceneRef.current && !leftHandMeshRef.current && !rightHandMeshRef.current) {
      const cubeGeometry = new THREE.BoxGeometry(0.05, 0.05, 0.05);
      const cubeMaterial = new THREE.MeshLambertMaterial({ color: 0xff0000 });

      const leftCube = new THREE.Mesh(cubeGeometry, cubeMaterial);
      const rightCube = new THREE.Mesh(cubeGeometry, cubeMaterial);

      leftCube.visible = false;
      rightCube.visible = false;

      leftHandMeshRef.current = leftCube;
      rightHandMeshRef.current = rightCube;

      threeSceneRef.current.add(leftCube);
      threeSceneRef.current.add(rightCube);
    }
  };

  // Handle controller input for pause toggle
  const handleControllerInput = (frame: any, referenceSpace: any) => {
    if (!frame || !referenceSpace) return;

    const inputSources = frame.session.inputSources;
    
    for (const inputSource of inputSources) {
      if (!inputSource.gamepad) continue;
      
      const gamepad = inputSource.gamepad;
      const hand = inputSource.handedness; // 'left' or 'right'
      
      // Create unique key for this controller
      const controllerKey = `${hand}-controller`;
      
      // Left controller X button (try multiple button indices as Quest mapping can vary)
      if (hand === 'left' && gamepad.buttons) {
        // Try button indices 2, 3, and 4 (X button location varies)
        let buttonIndex = 4;
        if (gamepad.buttons[2]) {
          const currentPressed = gamepad.buttons[buttonIndex].pressed;
          const stateKey = `${controllerKey}-${buttonIndex}`;
          const previousPressed = previousButtonStatesRef.current.get(stateKey) || false;
          
          // Only trigger on button press (not hold)
          if (currentPressed && !previousPressed) {
            updateStatus('Commands Paused (Press X on left controller to resume)'+ buttonIndex +  !pauseCommandsRef.current);
            pauseCommandsRef.current = !pauseCommandsRef.current;
          }
          
          // Update previous state
          previousButtonStatesRef.current.set(stateKey, currentPressed);
        }
        
      }
    }
  };

  // Create spheres that mark the exact controller STL attach points
  const createControllerSpheres = () => {
    if (!threeSceneRef.current) return;
    const scene = threeSceneRef.current;
    const geometry = new THREE.SphereGeometry(0.02, 32, 32);
    const material = new THREE.MeshLambertMaterial({ color: 0x00ffff, transparent: false, opacity: 1.0 });

    if (!leftSphereRef.current) {
      const left = new THREE.Mesh(geometry, material);
      left.visible = false;
      leftSphereRef.current = left;
      scene.add(left);
    }

    if (!rightSphereRef.current) {
      const right = new THREE.Mesh(geometry, material);
      right.visible = false;
      rightSphereRef.current = right;
      scene.add(right);
    }
  };

  // Load URDF robot after scene is initialized
  const loadURDFRobot = () => {
    if (threeSceneRef.current && !robotRef.current) {
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
          robotRef.current = robot;
          
          // Scale the robot to a reasonable size
          robot.scale.setScalar(1);
          
          // Position the robot in front of the camera
          robot.position.set(0, -0.239, 0);
          
          // Rotate robot 90 degrees around X-axis to point straight up
          robot.rotation.x = Math.PI /-2; // 90 degrees in radians
          robot.rotation.z = Math.PI / 2;
          // Make robot visible
          robot.visible = true;
          
          threeSceneRef.current.add(robot);
          
          setReady(true);
        },
        (progress) => {
          // Progress callback
        },
        (error) => {
          console.error('Error loading URDF:', error);
        }
      );
    }
  };

  // Initialize Three.js scene
  const initThreeScene = () => {
    if (!threeSceneRef.current) {
      const scene = new THREE.Scene();
      
      // Set a background color
      scene.background = new THREE.Color(0x222222);
      
      // Add basic lighting
      const ambientLight = new THREE.AmbientLight(0xffffff, 0.8);
      scene.add(ambientLight);
      
      const directionalLight = new THREE.DirectionalLight(0xffffff, 0.6);
      directionalLight.position.set(1, 1, 1);
      scene.add(directionalLight);
      
      threeSceneRef.current = scene;
      console.log('Three.js scene initialized');
      // Ensure controller spheres exist
      createControllerSpheres();
    }
  };

  // Process joint array (left or right) - convert indices to URDF joint names
  const processJointArray = (side: string, jointArray: number[]) => {
    if (!wsMapData || !wsMapData[side]) {
      console.error(`No mapping found for side: ${side}`);
      return;
    }
    
    if (!robotRef.current) {
      console.warn('Robot not loaded yet');
      return;
    }
    
    const jointUpdates: { [key: string]: number } = {};
    
    jointArray.forEach((angleInRadians, index) => {
      const jointName = wsMapData[side][index.toString()];
      if (jointName && robotRef.current?.joints[jointName]) {
        // Store update for batch processing
        jointUpdates[jointName] = angleInRadians;
        
        // Update robot joint immediately
        robotRef.current.joints[jointName].setJointValue(angleInRadians);
      } else {
        console.warn(`Joint not found for ${side}[${index}]: ${jointName}`);
      }
    });
    
    console.log(`Updated ${Object.keys(jointUpdates).length} joints for ${side} arm`);
  };

  // Update STL mesh positions based on hand tracking
  const updateMeshPositions = (handPositions: any) => {
    if (!threeSceneRef.current) return;
    
    // Add meshes to scene if they exist but aren't added yet
    if (leftHandMeshRef.current && !threeSceneRef.current.children.includes(leftHandMeshRef.current)) {
      threeSceneRef.current.add(leftHandMeshRef.current);
    }
    if (rightHandMeshRef.current && !threeSceneRef.current.children.includes(rightHandMeshRef.current)) {
      threeSceneRef.current.add(rightHandMeshRef.current);
    }
    
    // Update left hand mesh
    if (handPositions.left && leftHandMeshRef.current) {
      const position = handPositions.left.position;
      const orientation = handPositions.left.orientation;
 
      leftHandMeshRef.current.position.set(position[0], position[1], position[2]);
      leftHandMeshRef.current.quaternion.set(orientation[0], orientation[1], orientation[2], orientation[3]);
      leftHandMeshRef.current.visible = true;
      if (leftSphereRef.current) {
        leftSphereRef.current.position.set(position[0], position[1], position[2]);
        leftSphereRef.current.quaternion.set(orientation[0], orientation[1], orientation[2], orientation[3]);
        leftSphereRef.current.visible = true;
      }
    } else if (leftHandMeshRef.current) {
      leftHandMeshRef.current.visible = false;
      if (leftSphereRef.current) leftSphereRef.current.visible = false;
    }

    // Update right hand mesh
    if (handPositions.right && rightHandMeshRef.current) {
      const position = handPositions.right.position;
      const orientation = handPositions.right.orientation;
      rightHandMeshRef.current.position.set(position[0], position[1], position[2]);
      rightHandMeshRef.current.quaternion.set(orientation[0], orientation[1], orientation[2], orientation[3]);
      rightHandMeshRef.current.visible = true;
      if (rightSphereRef.current) {
        rightSphereRef.current.position.set(position[0], position[1], position[2]);
        rightSphereRef.current.quaternion.set(orientation[0], orientation[1], orientation[2], orientation[3]);
        rightSphereRef.current.visible = true;
      }
    } else if (rightHandMeshRef.current) {
      rightHandMeshRef.current.visible = false;
      if (rightSphereRef.current) rightSphereRef.current.visible = false;
    }

    // Hide meshes if no hand positions
    if (!handPositions.left && !handPositions.right) {
      if (leftHandMeshRef.current) leftHandMeshRef.current.visible = false;
      if (rightHandMeshRef.current) rightHandMeshRef.current.visible = false;
      if (leftSphereRef.current) leftSphereRef.current.visible = false;
      if (rightSphereRef.current) rightSphereRef.current.visible = false;
    }
  };

  const updateStatus = (msg: string) => {
    setStatus(msg);
  };

  const startVR = async () => {
    updateStatus('Starting VR URDF Viewer...');

    if (!navigator.xr) {
      updateStatus('WebXR not supported');
      alert('WebXR not supported in this browser');
      return;
    }

    const isVRSupported = await navigator.xr.isSessionSupported('immersive-vr');
    if (!isVRSupported) {
      updateStatus('VR not supported');
      alert('VR not supported in this browser');
      return;
    }

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
  
    threeRendererRef.current = renderer;
  
    // Request the XR session with appropriate features
    const session = await navigator.xr.requestSession('immersive-vr', {
      requiredFeatures: ['local-floor', 'viewer', 'hand-tracking'],
      optionalFeatures: ['layers'],
    });
    updateStatus('XR session created');
  
    // Hand the session to Three (this sets up XRWebGLLayer, etc.)
    await renderer.xr.setSession(session);
    updateStatus('Three.js XR session set');  
  
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
      // Reset camera position when exiting VR
      camera.position.set(0, 2, 2);
      camera.lookAt(0, 0, -2);
      updateStatus('Camera reset for non-VR view');
    });

    // Setup WS (non-blocking) for tracking data
    setupTrackingWebSocket().catch(err => {
      console.warn('WebSocket setup failed, continuing without it:', err);
      updateStatus('WebSocket connection failed, continuing with XR...');
    });
  
    // Init scene (lights, etc.)
    initThreeScene();
    
    // Load URDF robot after scene is ca
    loadURDFRobot();
  
     // Create a stable camera (Three will substitute XR camera internally)
     const camera = new THREE.PerspectiveCamera(
       75, // Field of view
       window.innerWidth / window.innerHeight, // Aspect ratio
       0.1, // Near plane
       100  // Far plane
     );
     
     // Manual camera orbiting (no OrbitControls needed for WebXR)
     
     // Handle resize
     const onResize = () => {
       camera.aspect = window.innerWidth / window.innerHeight;
       camera.updateProjectionMatrix();
       renderer.setSize(window.innerWidth, window.innerHeight);
     };
    window.addEventListener('resize', onResize);

    session.addEventListener('end', () => {
      updateStatus('XR session ended');
      window.removeEventListener('resize', onResize);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      // Clean up robot and hand meshes
      if (robotRef.current && threeSceneRef.current) {
        threeSceneRef.current.remove(robotRef.current);
        robotRef.current = null;
      }
      if (leftHandMeshRef.current && threeSceneRef.current) {
        threeSceneRef.current.remove(leftHandMeshRef.current);
        leftHandMeshRef.current = null;
      }
      if (rightHandMeshRef.current && threeSceneRef.current) {
        threeSceneRef.current.remove(rightHandMeshRef.current);
        rightHandMeshRef.current = null;
      }
      if (redSphereRef.current && threeSceneRef.current) {
        threeSceneRef.current.remove(redSphereRef.current);
        redSphereRef.current = null;
      }
      if (videoPlaneMeshRef.current && threeSceneRef.current) {
        threeSceneRef.current.remove(videoPlaneMeshRef.current);
        videoPlaneMeshRef.current = null;
      }
      if (statusPlaneMeshRef.current && threeSceneRef.current) {
        threeSceneRef.current.remove(statusPlaneMeshRef.current);
        statusPlaneMeshRef.current = null;
      }
    });

    // Use Three's XR render loop to obtain XRFrame
    renderer.setAnimationLoop((time, frame) => {
      if (!frame || !threeSceneRef.current) return;
      
      // Handle controller input for pause toggle
      handleControllerInput(frame, refSpace);
      
      // Tracking → positions/orientations → STL mesh updates
      let handPositions = null;
      if (hands) {
        handPositions = handleHandTracking(frame, refSpace, wsRef, lastHandSendRef);
      } else {
        handPositions = handleControllerTracking(frame, refSpace, wsRef, lastHandSendRef, pauseCommandsRef.current);
      }
      if (handPositions) updateMeshPositions(handPositions);

      renderer.render(threeSceneRef.current, camera);
    });
  };

  const setupTrackingWebSocket = () => {
    return new Promise((resolve, reject) => {
      try {
        let webSocket = new WebSocket(url);
        
        webSocket.onopen = () => {
          webSocket.send(JSON.stringify({
            role: "teleop",
            robot_id: "motion",
            control_type: hands ? "hand" : "controller"
          }));
          wsRef.current = webSocket;
          updateStatus('Hand tracking WebSocket connected');
          resolve(true);
        };

        webSocket.onmessage = (event) => {
          const data = JSON.parse(event.data);
          if (data.type === "joints") {
            // Process left and right joint arrays
            if (data.left && Array.isArray(data.left)) {
              processJointArray('left', data.left);
            }
            
            if (data.right && Array.isArray(data.right)) {
              processJointArray('right', data.right);
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

  return (
    <div style={{ padding: '20px', fontFamily: 'Arial, sans-serif' }}>
      {!started && (
        <div style={{ marginBottom: '20px' }}>
          <button
            onClick={() => { 
              setStarted(true); 
              startVR(); 
            }}
            style={{ 
              padding: '15px 30px', 
              fontSize: '18px', 
              backgroundColor: '#007bff',
              color: 'white',
              border: 'none',
              borderRadius: '5px',
              cursor: 'pointer'
            }}
          >
            Start VR Robot ({hands ? 'Hand' : 'Controller'} Tracking)
          </button>
        </div>
      )}
      
      {status && (
        <div style={{ 
          marginBottom: '20px', 
          padding: '10px', 
          backgroundColor: 'red', 
          border: '1px solid #dee2e6', 
          borderRadius: '4px'
        }}>
          Status: {status}
        </div>
      )}
      
      <video
        ref={videoRef}
        style={{ display: 'none' }}
        muted
        playsInline
        autoPlay
      />
      
      <canvas 
        ref={canvasRef} 
        style={{ 
          width: '100%', 
          height: '400px',
          border: '1px solid #ccc',
          display: started ? 'block' : 'none'
        }} 
      />
    </div>
  );
}
