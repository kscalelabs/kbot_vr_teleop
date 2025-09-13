import React, { useRef, useState, useEffect } from 'react';
import * as THREE from 'three';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js';
import { handleHandTracking, handleControllerTracking } from './webxrTracking';

interface BillboardProps {
  stream: MediaStream | null;
  url: string;
  hands: boolean;
}

export default function Billboard({ stream, url, hands }: BillboardProps) {
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
  const videoPlaneMeshRef = useRef<THREE.Mesh|null>(null);
  const videoTextureRef = useRef<THREE.VideoTexture|null>(null);
  const [stlReady, setStlReady] = useState(false);
  
  useEffect(() => {
    // Use the first available stream for the billboard
    if (videoRef.current && stream) {
      videoRef.current.srcObject = stream;
      videoRef.current.play().catch(e => console.log(`Video play warning: ${e.message}`));
    }
  }, [stream]);

  // Create video plane when stream and scene are ready
  useEffect(() => {
    if (stream && videoRef.current && threeSceneRef.current && !videoPlaneMeshRef.current) {
      // Create video texture
      const videoTexture = new THREE.VideoTexture(videoRef.current);
      videoTexture.minFilter = THREE.LinearFilter;
      videoTexture.magFilter = THREE.LinearFilter;
      videoTextureRef.current = videoTexture;

      // Create curved billboard geometry matching video aspect ratio (1280x1080)
      const videoAspectRatio = 1280 / 1080; // 1.185
      const height = 2.0;
      const width = height * videoAspectRatio; // Maintain video aspect ratio
      const segments = 32;
      const planeGeometry = new THREE.PlaneGeometry(width, height, segments, segments);
      
      // No curvature - keep plane flat

      // Create material with video texture
      const planeMaterial = new THREE.MeshBasicMaterial({ 
        map: videoTexture,
        side: THREE.DoubleSide
      });

      // Create mesh and position it
      const videoPlaneMesh = new THREE.Mesh(planeGeometry, planeMaterial);
      videoPlaneMesh.position.set(0, 0, -2); // Position in front of user
      
      videoPlaneMeshRef.current = videoPlaneMesh;
      threeSceneRef.current.add(videoPlaneMesh);
    }
  }, [stream, threeSceneRef.current]);

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
        const targetSize = 0.1;
        const scale = targetSize / maxDimension;
        
        console.log('STL dimensions:', size);
        console.log('Calculated scale:', scale);
        
        // Apply scale and flip on all axes
        leftMesh.scale.set(-scale, -scale, -scale);
        rightMesh.scale.set(-scale, -scale, -scale);

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

        setStlReady(true);
        console.log('STL model loaded successfully');
        console.log('STL bounding box:', geometry.boundingBox);
        console.log('STL scale applied:', scale);
      },
      (progress) => {
        console.log('STL loading progress:', (progress.loaded / progress.total * 100) + '%');
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
      
      setStlReady(true);
    }
  };

  // Initialize Three.js scene for cube rendering
  const initThreeScene = () => {
    if (!threeSceneRef.current) {
      const scene = new THREE.Scene();
      
      // Add lighting for the cubes
      const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
      scene.add(ambientLight);
      
      const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
      directionalLight.position.set(1, 1, 1);
      scene.add(directionalLight);
      
      threeSceneRef.current = scene;
    }
  };

  // Update STL mesh positions based on hand tracking
  const updateMeshPositions = (handPositions: any) => {
    if (!threeSceneRef.current || !stlReady) return;
    
    // Add meshes to scene if they exist but aren't added yet
    if (leftHandMeshRef.current && !threeSceneRef.current.children.includes(leftHandMeshRef.current)) {
      threeSceneRef.current.add(leftHandMeshRef.current);
    }
    if (rightHandMeshRef.current && !threeSceneRef.current.children.includes(rightHandMeshRef.current)) {
      threeSceneRef.current.add(rightHandMeshRef.current);
    }
    
    // Update left hand mesh
    if (handPositions.left && leftHandMeshRef.current) {
      const { position, orientation } = handPositions.left;
      leftHandMeshRef.current.position.set(position.x, position.y, position.z);
      leftHandMeshRef.current.quaternion.set(orientation.x, orientation.y, orientation.z, orientation.w);
      leftHandMeshRef.current.visible = true;
    } else if (leftHandMeshRef.current) {
      leftHandMeshRef.current.visible = false;
    }

    // Update right hand mesh
    if (handPositions.right && rightHandMeshRef.current) {
      const { position, orientation } = handPositions.right;
      rightHandMeshRef.current.position.set(position.x, position.y, position.z);
      rightHandMeshRef.current.quaternion.set(orientation.x, orientation.y, orientation.z, orientation.w);
      rightHandMeshRef.current.visible = true;
    } else if (rightHandMeshRef.current) {
      rightHandMeshRef.current.visible = false;
    }

    // Hide meshes if no hand positions
    if (!handPositions.left && !handPositions.right) {
      if (leftHandMeshRef.current) leftHandMeshRef.current.visible = false;
      if (rightHandMeshRef.current) rightHandMeshRef.current.visible = false;
    }
  };

  const updateStatus = (msg: string) => {
    setStatus(msg);
  };

  const startVR = async () => {
    updateStatus('Starting VR Billboard...');

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
    renderer.xr.setReferenceSpaceType('viewer');
  
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
  
    // Setup WS (non-blocking) for tracking data
    await setupTrackingWebSocket().catch(err => {
      console.warn('WebSocket setup failed, continuing without it:', err);
      updateStatus('WebSocket connection failed, continuing with XR...');
    });
  
    // Init scene (lights, etc.). Your video plane effect will attach once the scene exists.
    initThreeScene();
  
     // Create a stable camera (Three will substitute XR camera internally)
     // Video aspect ratio: 1280x1080 = 1.185
     const videoAspectRatio = 1280 / 1080;
     const camera = new THREE.PerspectiveCamera(
       75, // Wider field of view to better frame the video
       videoAspectRatio, // Match camera aspect ratio to video
       0.01,
       100
     );
  
     // Position camera to look directly at the center of the video plane
     camera.position.set(0, 0, 0); // Camera at origin
     camera.lookAt(0, 0, -2); // Look at center of video plane (which is at z=-2)
     
     // Handle resize
     const onResize = () => {
       // Keep camera aspect ratio matched to video, not window
       camera.aspect = videoAspectRatio;
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
    });

    // Use Three's XR render loop to obtain XRFrame
    renderer.setAnimationLoop((time, frame) => {
      if (!frame || !threeSceneRef.current) return;
      
      // Tracking → positions/orientations → STL mesh updates
      let handPositions = null;
       if (hands) {
         handPositions = handleHandTracking(frame, refSpace, wsRef, lastHandSendRef);
       } else {
         handPositions = handleControllerTracking(frame, refSpace, wsRef, lastHandSendRef);
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
            robot_id: "motion"
          }));
          wsRef.current = webSocket;
          updateStatus('Hand tracking WebSocket connected');
          resolve(true);
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
            Start VR Billboard ({hands ? 'Hand' : 'Controller'} Tracking)
          </button>
        </div>
      )}
      
      {status && (
        <div style={{ 
          marginBottom: '20px', 
          padding: '10px', 
          backgroundColor: '#f8f9fa', 
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