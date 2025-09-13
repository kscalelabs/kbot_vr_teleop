import React, { useRef, useEffect, useState } from "react";

export default function ShaderTest() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [status, setStatus] = useState("");

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.src = "/left_web.mp4";
    video.muted = true;
    video.playsInline = true;
    video.load();
    video.play().catch(() => {});

    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl");
    if (!gl) {
      setStatus("WebGL not supported");
      return;
    }

    // Shader code (copied from Sphere.tsx, with correction)
    const vertexShaderSource = `
      attribute vec3 position;
      varying vec3 vPos;
      void main() {
        vPos = position;
        gl_Position = vec4(position, 1.0);
        gl_PointSize = 10.0;
      }
    `;
    const fragmentShaderSource = `
      precision mediump float;
      varying vec3 vPos;
      uniform sampler2D videoTexture;
      uniform vec2 imgSize;
      void main() {
        float k1 = 0.0;
        float k2 = 0.01;
        float fx = 300.0;
        float fy = 300.0;
        float cx = 640.0;
        float cy = 540.0;
        float a = vPos.x / vPos.z;
        float b = vPos.y / vPos.z;
        float r = sqrt(a * a + b * b);
        float theta = atan(r, 1.0);
        float theta_d = theta * (1.0 + k1 * theta * theta + k2 * theta * theta * theta * theta);
        float x_prime = (theta_d / r) * a;
        float y_prime = (theta_d / r) * b;
        float u = fx * x_prime + cx;
        float v = fy * y_prime + cy;
        vec2 uv = vec2(u, v) / imgSize;
        if (r > 1.0 || uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
          gl_FragColor = vec4(0.0,0.0,0.0,1.0);
        } else {
          gl_FragColor = texture2D(videoTexture, uv);
        }
      }
    `;

    function compileShader(src: string, type: number) {
      const shader = gl.createShader(type)!;
      gl.shaderSource(shader, src);
      gl.compileShader(shader);
      return shader;
    }

    const program = gl.createProgram()!;
    gl.attachShader(program, compileShader(vertexShaderSource, gl.VERTEX_SHADER));
    gl.attachShader(program, compileShader(fragmentShaderSource, gl.FRAGMENT_SHADER));
    gl.linkProgram(program);
    gl.useProgram(program);

    // Sphere mesh
    const segments = 128;
    const sphereRadius = 1.0;
    const positions: number[] = [];
    const indices: number[] = [];
    for (let y = 0; y <= segments; y++) {
      const theta = (y / segments) * Math.PI;
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

    // Texture
    const texture = gl.createTexture()!;
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    const videoTextureLoc = gl.getUniformLocation(program, "videoTexture");
    const imgSizeLoc = gl.getUniformLocation(program, "imgSize");
    gl.uniform1i(videoTextureLoc, 0);
    gl.uniform2f(imgSizeLoc, 1280.0, 1080.0);

    function render() {
      gl.clearColor(0, 0, 0, 1);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, texture);
      if (video.readyState >= 2) {
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, video);
      }
      gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
      gl.enableVertexAttribArray(positionLoc);
      gl.vertexAttribPointer(positionLoc, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, indexBuffer);
      gl.drawElements(gl.TRIANGLES, indices.length, gl.UNSIGNED_SHORT, 0);
      requestAnimationFrame(render);
    }
    render();
  }, []);

  return (
    <div style={{ padding: "20px" }}>
      <div>{status}</div>
      <video ref={videoRef} style={{ display: "none" }} />
      <canvas ref={canvasRef} width={1280} height={1080} style={{ width: "100%", height: "400px" }} />
    </div>
  );
}
