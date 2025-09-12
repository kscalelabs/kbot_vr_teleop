import React, { useRef, useState, useEffect } from "react";
import { handleHandTracking, handleControllerTracking } from './webxrTracking';

const flipCenter = (centerX: number, centerY: number, width: number, height: number) => {
  return [centerX, centerY];
};

interface BillboardProps {
  stream1: MediaStream | null;
  stream2: MediaStream | null;
  url: string;
}

export default function Billboard({ stream1, stream2, url }: BillboardProps) {
  const wsRef = useRef<WebSocket | null>(null);
  const lastHandSendRef = useRef(0);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const videoRef1 = useRef<HTMLVideoElement>(null);
  const videoRef2 = useRef<HTMLVideoElement>(null);
  const [started, setStarted] = useState(false);
  const [status, setStatus] = useState("");

  useEffect(() => {
    if (videoRef1.current && stream1) {
      videoRef1.current.srcObject = stream1;
      videoRef1.current.play().catch((e) =>
        console.log(`Video 1 play warning: ${e.message}`)
      );
    }
    if (videoRef2.current && stream2) {
      videoRef2.current.srcObject = stream2;
      videoRef2.current.play().catch((e) =>
        console.log(`Video 2 play warning: ${e.message}`)
      );
    }
  }, [stream1, stream2]);

  const updateStatus = (msg: string) => setStatus(msg);

  const startVR = async () => {
    // Setup WebSocket connection for hand tracking data (example)
    if (!wsRef.current) {
      wsRef.current = new WebSocket(url);
      wsRef.current.onopen = () => {
        wsRef.current!.send(JSON.stringify({ role: "teleop", robot_id: "motion" }));
      };
    }
    updateStatus("Starting VR Billboard...");
  
    if (!navigator.xr) {
      alert("WebXR not supported in this browser");
      return;
    }
    const isVRSupported = await navigator.xr.isSessionSupported("immersive-vr");
    if (!isVRSupported) {
      alert("VR not supported in this browser");
      return;
    }
  
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl", { xrCompatible: true }) as WebGLRenderingContext;
    if (!gl) {
      updateStatus("WebGL not supported");
      return;
    }
  
    const video1 = videoRef1.current!;
    const video2 = videoRef2.current!;
  
    video1.muted = true;
    video1.playsInline = true;
    video2.muted = true;
    video2.playsInline = true;
  
    // Wait for videos to be ready
    const videoPromises: Promise<void>[] = [];
  
    if (stream1) {
      videoPromises.push(new Promise<void>((resolve, reject) => {
        if (video1.readyState >= 2) return resolve();
        const onLoaded = () => { video1.removeEventListener("loadeddata", onLoaded); resolve(); };
        video1.addEventListener("loadeddata", onLoaded);
        video1.addEventListener("error", () => reject(new Error("Video 1 failed to load")));
        video1.load();
      }));
    }
    if (stream2) {
      videoPromises.push(new Promise<void>((resolve, reject) => {
        if (video2.readyState >= 2) return resolve();
        const onLoaded = () => { video2.removeEventListener("loadeddata", onLoaded); resolve(); };
        video2.addEventListener("loadeddata", onLoaded);
        video2.addEventListener("error", () => reject(new Error("Video 2 failed to load")));
        video2.load();
      }));
    }
    if (videoPromises.length > 0) await Promise.all(videoPromises);
  
    if (stream1) await video1.play();
    if (stream2) await video2.play();
    updateStatus("Videos playing");
  
    // ======================
    // SHADERS
    // ======================
    const vertexShaderSource = `
      attribute vec3 position;
      varying vec3 vPos;
      uniform mat4 viewMatrix;
      uniform mat4 projectionMatrix;
  
      void main() {
          vPos = position;
          mat4 rotOnlyView = mat4(
              vec4(viewMatrix[0][0], viewMatrix[0][1], viewMatrix[0][2], 0.0),
              vec4(viewMatrix[1][0], viewMatrix[1][1], viewMatrix[1][2], 0.0),
              vec4(viewMatrix[2][0], viewMatrix[2][1], viewMatrix[2][2], 0.0),
              vec4(0.0, 0.0, 0.0, 1.0)
          );
          gl_Position = projectionMatrix * rotOnlyView * vec4(position,1.0);
          gl_PointSize = 10.0; // size for center dot
      }
    `;
  
    const fragmentShaderSource = `
      precision mediump float;
      varying vec3 vPos;
      uniform sampler2D videoTexture;
      uniform vec2 center;
      uniform float radius;
      uniform vec2 imgSize;
      uniform int isCenter;
  
      void main() {
          if (isCenter == 1) {
              gl_FragColor = vec4(1.0,0.0,0.0,1.0); // red dot
              return;
          }
          vec3 dir = normalize(vPos);
          float theta = atan(dir.y, dir.x);
          float phi = atan(length(dir.xy), dir.z);
          float rr = phi / radians(110.0);
          vec2 uv = center + rr * radius * vec2(cos(theta), sin(theta));
          uv /= imgSize;
          uv.y = 1.0 - uv.y;
          if (rr > 1.0) {
              gl_FragColor = vec4(0.0,0.0,0.0,1.0);
          } else {
              gl_FragColor = texture2D(videoTexture, uv);
          }
      }
    `;
  
    const compileShader = (src: string, type: number) => {
      const shader = gl.createShader(type)!;
      gl.shaderSource(shader, src);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        console.error("Shader error:", gl.getShaderInfoLog(shader));
      }
      return shader;
    };
  
    const program = gl.createProgram()!;
    gl.attachShader(program, compileShader(vertexShaderSource, gl.VERTEX_SHADER));
    gl.attachShader(program, compileShader(fragmentShaderSource, gl.FRAGMENT_SHADER));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.error("Program link error:", gl.getProgramInfoLog(program));
    }
    gl.useProgram(program);
  
    // ================
    // SPHERE MESH
    // ================
    const segments = 1024;
    const sphereRadius = 1.0;
    const positions: number[] = [];
    const indices: number[] = [];
  
    for (let y = 0; y <= segments; y++) {
      const theta = (y / segments) * (Math.PI * 220 / 360);
      for (let x = 0; x <= segments; x++) {
        const phi = (x / segments) * 2.0 * Math.PI;
        positions.push(
          sphereRadius * Math.sin(theta) * Math.cos(phi),
          sphereRadius * Math.sin(theta) * Math.sin(phi),
          sphereRadius * Math.cos(theta)
        );
      }
    }
  
    for (let y = 0; y < segments; y++) {
      for (let x = 0; x < segments; x++) {
        const i = y * (segments + 1) + x;
        indices.push(i, i + 1, i + segments + 1);
        indices.push(i + 1, i + segments + 2, i + segments + 1);
      }
    }
  
    const positionBuffer = gl.createBuffer()!;
    gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(positions), gl.STATIC_DRAW);
  
    const indexBuffer = gl.createBuffer()!;
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, indexBuffer);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array(indices), gl.STATIC_DRAW);
  
    const positionLoc = gl.getAttribLocation(program, "position");
  
    // ================
    // TEXTURES
    // ================
    const texture1 = gl.createTexture()!;
    const texture2 = gl.createTexture()!;
    [texture1, texture2].forEach(tex => {
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    });
  
    const videoTextureLoc = gl.getUniformLocation(program, "videoTexture");
    const centerLoc = gl.getUniformLocation(program, "center");
    const radiusLoc = gl.getUniformLocation(program, "radius");
    const imgSizeLoc = gl.getUniformLocation(program, "imgSize");
    const viewMatrixLoc = gl.getUniformLocation(program, "viewMatrix");
    const projectionMatrixLoc = gl.getUniformLocation(program, "projectionMatrix");
    const isCenterLoc = gl.getUniformLocation(program, "isCenter");
  
    gl.uniform1i(videoTextureLoc, 0);
    gl.uniform2f(imgSizeLoc, 1280.0, 1080.0);
  
    // ================
    // XR SESSION
    // ================
    let session: XRSession;
    try {
      session = await navigator.xr.requestSession("immersive-vr", { optionalFeatures: ["hand-tracking"] });
    } catch (err) {
      updateStatus(`Failed to start XR session: ${err}`);
      return;
    }
  
    await gl.makeXRCompatible();
    session.updateRenderState({ baseLayer: new XRWebGLLayer(session, gl) });
    const refSpace = await session.requestReferenceSpace("local");
  
    // Utility: compute 3D center point for dot
    const computeCenter3D = (cx: number, cy: number) => {
      const nx = (cx / 1280) * 2 - 1;
      const ny = (cy / 1080) * 2 - 1;
      const phi = nx * (Math.PI * 220 / 360);
      const theta = ny * 2 * Math.PI;
      const r = 1.0;
      return [r * Math.sin(phi) * Math.cos(theta), r * Math.sin(phi) * Math.sin(theta), r * Math.cos(phi)];
    };
  
    const centerPointLeft = computeCenter3D(634, 446);
    const centerPointRight = computeCenter3D(686, 516);
  
    const centerBuffer = gl.createBuffer()!;
  
    const onXRFrame = (time: DOMHighResTimeStamp, frame: XRFrame) => {
      // Example: send hand tracking data if WebSocket is open
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        handleHandTracking(frame, refSpace, wsRef, lastHandSendRef);
      }
      const pose = frame.getViewerPose(refSpace);
      if (!pose) {
        session.requestAnimationFrame(onXRFrame);
        return;
      }
  
      gl.bindFramebuffer(gl.FRAMEBUFFER, session.renderState.baseLayer!.framebuffer);
      gl.clearColor(0, 0, 0, 1);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  
      pose.views.forEach((view, eyeIndex) => {
        const viewport = session.renderState.baseLayer!.getViewport(view)!;
        gl.viewport(viewport.x, viewport.y, viewport.width, viewport.height);
  
        const video = eyeIndex === 0 ? video1 : video2;
        const tex = eyeIndex === 0 ? texture1 : texture2;
        const center3D = eyeIndex === 0 ? centerPointLeft : centerPointRight;
        const radius = eyeIndex === 0 ? 541.0 : 538.0;
        const center2D = eyeIndex === 0 ? [634.0, 446.0] : [686.0, 516.0];
  
        // bind video texture
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, tex);
        if (video && video.readyState >= 2) {
          gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, video);
        }
  
        // bind uniforms
        gl.uniform2f(centerLoc, center2D[0], center2D[1]);
        gl.uniform1f(radiusLoc, radius);
        gl.uniformMatrix4fv(viewMatrixLoc, false, view.transform.inverse.matrix as Float32Array);
        gl.uniformMatrix4fv(projectionMatrixLoc, false, view.projectionMatrix);
  
        // draw sphere
        gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
        gl.enableVertexAttribArray(positionLoc);
        gl.vertexAttribPointer(positionLoc, 3, gl.FLOAT, false, 0, 0);
        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, indexBuffer);
        gl.uniform1i(isCenterLoc, 0);
        gl.drawElements(gl.TRIANGLES, indices.length, gl.UNSIGNED_SHORT, 0);
  
        // draw red center dot
        gl.bindBuffer(gl.ARRAY_BUFFER, centerBuffer);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(center3D), gl.STATIC_DRAW);
        gl.enableVertexAttribArray(positionLoc);
        gl.vertexAttribPointer(positionLoc, 3, gl.FLOAT, false, 0, 0);
        gl.uniform1i(isCenterLoc, 1);
        gl.drawArrays(gl.POINTS, 0, 1);
        gl.uniform1i(isCenterLoc, 0);
      });
  
      session.requestAnimationFrame(onXRFrame);
    };
  
    session.requestAnimationFrame(onXRFrame);
  };
  

  return (
    <div style={{ padding: "20px" }}>
      {!started && (
        <button onClick={async () => { setStarted(true); await startVR(); }}>
          Start VR Dual Stream Billboard
        </button>
      )}
      <div>{status}</div>
      <video ref={videoRef1} style={{ display: "none" }} muted playsInline />
      <video ref={videoRef2} style={{ display: "none" }} muted playsInline />
      <canvas ref={canvasRef} style={{ width: "100%", height: "400px" }} />
    </div>
  );
}