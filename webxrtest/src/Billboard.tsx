import React, { useRef, useState, useEffect } from 'react';
import { handleHandTracking, handleControllerTracking } from './webxrTracking';
import * as THREE from 'three';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader';
import { renderSTLGeometry, renderTestRing } from './stlGlRenderer';

interface BillboardProps {
  stream: MediaStream | null;
  url: string;
  hands: boolean;
}

export default function Billboard({ stream, url, hands }: BillboardProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const lastHandSendRef = useRef(0);
  const [started, setStarted] = useState(false);
  const [status, setStatus] = useState('');
  const [stlReady, setStlReady] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const stlGeometriesRef = useRef<{left: THREE.BufferGeometry|null, right: THREE.BufferGeometry|null}>({left: null, right: null});
  const threeSceneRef = useRef<THREE.Scene|null>(null);
  const threeRendererRef = useRef<THREE.WebGLRenderer|null>(null);
  const stlLoadedRef = useRef(false);
  
  useEffect(() => {
    // Use the first available stream for the billboard
    if (videoRef.current && stream) {
      videoRef.current.srcObject = stream;
      videoRef.current.play().catch(e => console.log(`Video play warning: ${e.message}`));
    }
  }, [stream]);

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

    const gl = canvas.getContext('webgl', { xrCompatible: true }) as WebGLRenderingContext | null;
    if (!gl) {
      updateStatus('WebGL not supported');
      return;
    }

    const video = videoRef.current!;
    video.muted = true;
    video.playsInline = true;
    video.preload = 'metadata';

    updateStatus('Loading video...');

    let videoReady = false;
    if (true) {
      try {
        await new Promise<void>((resolve, reject) => {
          if (video.readyState >= 2) {
            resolve();
            return;
          }
          const onLoadedData = () => {
            video.removeEventListener('loadeddata', onLoadedData);
            video.removeEventListener('error', onError);
            resolve();
          };
          const onError = () => {
            video.removeEventListener('loadeddata', onLoadedData);
            video.removeEventListener('error', onError);
            reject(new Error(`Video failed to load`));
          };
          video.addEventListener('loadeddata', onLoadedData);
          video.addEventListener('error', onError);
          video.load();
        });
        await video.play();
        videoReady = true;
        updateStatus('Video playing');
      } catch (err) {
        updateStatus(`Video error: ${err}`);
        // Continue to launch VR even if video fails
      }
    } else {
      updateStatus('No stream provided, continuing to launch VR.');
    }

    // Shaders for curved billboard
    const vertexShaderSource = `
      attribute vec3 position;
      attribute vec2 uv;
      varying vec2 vUV;
      uniform mat4 projectionMatrix;
      uniform mat4 modelViewMatrix;
      
      void main() {
        vUV = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `;

    const fragmentShaderSource = `
      precision mediump float;
      varying vec2 vUV;
      uniform sampler2D videoTexture;
      
      void main() {
        vec4 color = texture2D(videoTexture, vUV);
        gl_FragColor = color;
      }
    `;

    const compileShader = (src: string, type: number) => {
      const shader = gl.createShader(type)!;
      gl.shaderSource(shader, src);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        const error = gl.getShaderInfoLog(shader);
        updateStatus(`Shader compile error: ${error}`);
      }
      return shader;
    };

    const vertexShader = compileShader(vertexShaderSource, gl.VERTEX_SHADER);
    const fragmentShader = compileShader(fragmentShaderSource, gl.FRAGMENT_SHADER);

    const program = gl.createProgram()!;
    gl.attachShader(program, vertexShader);
    gl.attachShader(program, fragmentShader);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      const error = gl.getProgramInfoLog(program);
      updateStatus(`Programlink error: ${error}`);
    }
    gl.useProgram(program);

    // Create flat billboard geometry
    const createCurvedBillboard = () => {
      const vertices: number[] = [];
      const uvs: number[] = [];
      const indices: number[] = [];
    
      // For 1280x1080 stream: width=1280, height=1080
      const streamWidth = 1280;
      const streamHeight = 1080;
      const aspectRatio = streamWidth / streamHeight; // 1280/1080 ≈ 1.185
      
      // Set comfortable dimensions for flat plane
      const maxHeight = 3.0; // Comfortable height for VR viewing
      const height = maxHeight;
      // Use full width since there's no curvature to compensate for
      const width = height * aspectRatio; // Full width for flat plane
      
      console.log(`Billboard base dimensions: ${width.toFixed(2)}w x ${height.toFixed(2)}h (aspect ratio: ${aspectRatio.toFixed(3)})`);
      
      const segments = 24; // Segments for smooth rendering
      const distance = 4.5; // Distance from origin
      
      // Generate vertices for flat surface
      for (let i = 0; i <= segments; i++) {
        for (let j = 0; j <= segments; j++) {
          const u = i / segments;
          const v = j / segments;
          
          // Map to billboard coordinates for flat plane
          const x = (u - 0.5) * width;
          const y = (v - 0.5) * height;
          
          // Create flat plane positioned in front of user
          const flatX = x;
          const flatY = y;
          const flatZ = -distance; // Fixed distance, no curvature
          
          vertices.push(flatX, flatY, flatZ);
          uvs.push(u, 1 - v); // Flip V coordinate to fix vertical flip
        }
      }
      
      // Generate indices for triangles
      for (let i = 0; i < segments; i++) {
        for (let j = 0; j < segments; j++) {
          const a = i * (segments + 1) + j;
          const b = a + segments + 1;
          
          // First triangle
          indices.push(a, b, a + 1);
          // Second triangle
          indices.push(b, b + 1, a + 1);
        }
      }
      
      return { vertices, uvs, indices };
    };

    const { vertices, uvs, indices } = createCurvedBillboard();

    // Create buffers
    const vertexBuffer = gl.createBuffer()!;
    gl.bindBuffer(gl.ARRAY_BUFFER, vertexBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(vertices), gl.STATIC_DRAW);

    const uvBuffer = gl.createBuffer()!;
    gl.bindBuffer(gl.ARRAY_BUFFER, uvBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(uvs), gl.STATIC_DRAW);

    const indexBuffer = gl.createBuffer()!;
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, indexBuffer);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array(indices), gl.STATIC_DRAW);

    // Get attribute and uniform locations
    const positionLoc = gl.getAttribLocation(program, 'position');
    const uvLoc = gl.getAttribLocation(program, 'uv');
    const projectionMatrixLoc = gl.getUniformLocation(program, 'projectionMatrix');
    const modelViewMatrixLoc = gl.getUniformLocation(program, 'modelViewMatrix');
    const videoUniformLoc = gl.getUniformLocation(program, 'videoTexture');

    // Create texture
    const texture = gl.createTexture()!;
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

    let session: XRSession;

    try {
      updateStatus('Requesting XR session...');
      session = await navigator.xr.requestSession('immersive-vr', {
        optionalFeatures: ['hand-tracking']
      });
      updateStatus('XR session created');
    } catch (err) {
      updateStatus(`Failed to start XR session: ${err}`);
      return;
    }

    await gl.makeXRCompatible();
    session.updateRenderState({ baseLayer: new XRWebGLLayer(session, gl) });

    const refSpace = await session.requestReferenceSpace('viewer');
    updateStatus('Reference space created, starting render loop...');

    // Setup WebSocket connection for hand tracking data
    await setupHandTrackingWebSocket();

    session.addEventListener('end', () => {
      updateStatus('XR session ended');
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    });

    // Matrix utilities
    const multiplyMatrices = (a: Float32Array, b: Float32Array): Float32Array => {
      const result = new Float32Array(16);
      for (let i = 0; i < 4; i++) {
        for (let j = 0; j < 4; j++) {
          result[i * 4 + j] = 
            a[i * 4 + 0] * b[0 * 4 + j] +
            a[i * 4 + 1] * b[1 * 4 + j] +
            a[i * 4 + 2] * b[2 * 4 + j] +
            a[i * 4 + 3] * b[3 * 4 + j];
        }
      }
      return result;
    };

    const createIdentityMatrix = () => {
      return new Float32Array([
        1, 0, 0, 0,
        0, 1, 0, 0,
        0, 0, 1, 0,
        0, 0, 0, 1
      ]);
    };

    // Create a fixed world-space model matrix for the billboard
    const createBillboardModelMatrix = () => {
      // Identity matrix - billboard stays in world space
      return createIdentityMatrix();
    };

    const onXRFrame = (time: DOMHighResTimeStamp, frame: XRFrame) => {
      const pose = frame.getViewerPose(refSpace);
      if (!pose) {
        session.requestAnimationFrame(onXRFrame);
        return;
      }

      // Handle hand/controller tracking (shared)
      if (hands) {
        handleHandTracking(frame, refSpace, wsRef, lastHandSendRef);
      } else {
        handleControllerTracking(frame, refSpace, wsRef, lastHandSendRef);
      }

      gl.bindFramebuffer(gl.FRAMEBUFFER, session.renderState.baseLayer!.framebuffer);
      gl.clearColor(0.0, 0.0, 0.0, 1);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      gl.enable(gl.DEPTH_TEST);

      pose.views.forEach((view) => {
        const viewport = session.renderState.baseLayer!.getViewport(view);
        if (!viewport) return;
        
        gl.viewport(viewport.x, viewport.y, viewport.width, viewport.height);

        // Check if video is ready
        if (video.readyState < 2 || video.videoWidth === 0 || video.videoHeight === 0) {
          return;
        }

        // Update texture with video frame
        gl.bindTexture(gl.TEXTURE_2D, texture);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, video);

        // Set up vertex attributes
        gl.bindBuffer(gl.ARRAY_BUFFER, vertexBuffer);
        gl.enableVertexAttribArray(positionLoc);
        gl.vertexAttribPointer(positionLoc, 3, gl.FLOAT, false, 0, 0);

        gl.bindBuffer(gl.ARRAY_BUFFER, uvBuffer);
        gl.enableVertexAttribArray(uvLoc);
        gl.vertexAttribPointer(uvLoc, 2, gl.FLOAT, false, 0, 0);

        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, indexBuffer);

        // Calculate proper model-view matrix
        const modelMatrix = createBillboardModelMatrix();
        const viewMatrix = view.transform.inverse.matrix;
        const modelViewMatrix = multiplyMatrices(viewMatrix, modelMatrix);

        // Set uniforms
        gl.uniformMatrix4fv(projectionMatrixLoc, false, view.projectionMatrix);
        gl.uniformMatrix4fv(modelViewMatrixLoc, false, modelViewMatrix);
        gl.uniform1i(videoUniformLoc, 0);

        // Draw the curved billboard
        gl.drawElements(gl.TRIANGLES, indices.length, gl.UNSIGNED_SHORT, 0);
      });

      session.requestAnimationFrame(onXRFrame);
    };

    session.requestAnimationFrame(onXRFrame);
  };

  const setupHandTrackingWebSocket = () => {
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

  // Load STL files only once
  if (!stlLoadedRef.current) {
    const loader = new STLLoader();
    loader.load('/PRT0001.stl', geometry => {
      stlGeometriesRef.current.left = geometry;
      if (stlGeometriesRef.current.right) setStlReady(true);
    });
    loader.load('/PRT0001_2.stl', geometry => {
      stlGeometriesRef.current.right = geometry;
      if (stlGeometriesRef.current.left) setStlReady(true);
    });
    stlLoadedRef.current = true;
  }

  return (
    <div style={{ padding: '20px', fontFamily: 'Arial, sans-serif' }}>
      {!started && (
        <div>
          <button
            style={{ 
              fontSize: '24px', 
              padding: '12px 24px',
              marginBottom: '20px',
              backgroundColor: '#007bff',
              color: 'white',
              border: 'none',
              borderRadius: '5px',
              cursor: 'pointer'
            }}
            onClick={async () => {
              setStarted(true);
              await startVR();
            }}
          >
            Start VR Billboard
          </button>
        </div>
      )}
      
      {status && (
        <div style={{ 
          padding: '10px', 
          backgroundColor: '#f8f9fa', 
          border: '1px solid #dee2e6', 
          borderRadius: '5px',
          marginBottom: '10px',
          fontSize: '14px'
        }}>
          Status: {status}
        </div>
      )}
      
      <video
        ref={videoRef}
        src="/left_web.mp4"
        crossOrigin="anonymous"
        style={{ display: 'none' }}
        muted
        playsInline
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
