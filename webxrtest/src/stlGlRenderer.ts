// Minimal STL renderer using raw WebGL (option 2)
// Usage: import { renderSTLGeometry } from './stlGlRenderer';
// Call renderSTLGeometry(gl, geometry, transform) in your XR frame loop

import * as THREE from 'three';

export function renderSTLGeometry(gl: WebGLRenderingContext, geometry: THREE.BufferGeometry, transform: THREE.Matrix4) {
  // Extract vertices and normals from geometry
  const positionAttr = geometry.getAttribute('position');
  const normalAttr = geometry.getAttribute('normal');
  if (!positionAttr || !normalAttr) return;

  // Create buffers
  const vertexBuffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, vertexBuffer);
  gl.bufferData(gl.ARRAY_BUFFER, positionAttr.array, gl.STATIC_DRAW);

  const normalBuffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, normalBuffer);
  gl.bufferData(gl.ARRAY_BUFFER, normalAttr.array, gl.STATIC_DRAW);

  // Simple vertex/fragment shaders for STL rendering
  const vertSrc = `
    attribute vec3 position;
    attribute vec3 normal;
    uniform mat4 modelMatrix;
    uniform mat4 viewMatrix;
    uniform mat4 projectionMatrix;
    varying vec3 vNormal;
    void main() {
      vNormal = normal;
      gl_Position = projectionMatrix * viewMatrix * modelMatrix * vec4(position, 1.0);
    }
  `;
  const fragSrc = `
    precision mediump float;
    varying vec3 vNormal;
    void main() {
      vec3 color = abs(vNormal);
      gl_FragColor = vec4(color, 1.0);
    }
  `;

  // Compile shaders and link program
  function compileShader(src: string, type: number) {
    const shader = gl.createShader(type)!;
    gl.shaderSource(shader, src);
    gl.compileShader(shader);
    return shader;
  }
  const vertShader = compileShader(vertSrc, gl.VERTEX_SHADER);
  const fragShader = compileShader(fragSrc, gl.FRAGMENT_SHADER);
  const program = gl.createProgram()!;
  gl.attachShader(program, vertShader);
  gl.attachShader(program, fragShader);
  gl.linkProgram(program);
  gl.useProgram(program);

  // Set up attributes
  const posLoc = gl.getAttribLocation(program, 'position');
  gl.bindBuffer(gl.ARRAY_BUFFER, vertexBuffer);
  gl.enableVertexAttribArray(posLoc);
  gl.vertexAttribPointer(posLoc, 3, gl.FLOAT, false, 0, 0);

  const normLoc = gl.getAttribLocation(program, 'normal');
  gl.bindBuffer(gl.ARRAY_BUFFER, normalBuffer);
  gl.enableVertexAttribArray(normLoc);
  gl.vertexAttribPointer(normLoc, 3, gl.FLOAT, false, 0, 0);

  // Set up uniforms
  const modelLoc = gl.getUniformLocation(program, 'modelMatrix');
  gl.uniformMatrix4fv(modelLoc, false, transform.elements);
  // For demo, use identity for view/projection
  const identity = new Float32Array([1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]);
  gl.uniformMatrix4fv(gl.getUniformLocation(program, 'viewMatrix'), false, identity);
  gl.uniformMatrix4fv(gl.getUniformLocation(program, 'projectionMatrix'), false, identity);

  // Draw geometry
  gl.drawArrays(gl.TRIANGLES, 0, positionAttr.count);

  // Cleanup
  gl.disableVertexAttribArray(posLoc);
  gl.disableVertexAttribArray(normLoc);
  gl.deleteBuffer(vertexBuffer);
  gl.deleteBuffer(normalBuffer);
  gl.deleteProgram(program);
  gl.deleteShader(vertShader);
  gl.deleteShader(fragShader);
}

export function renderTestRing(gl: WebGLRenderingContext) {
  // Create a ring of red triangles around the user
  const numTriangles = 24;
  const radius = 2.0;
  const vertices = [];
  for (let i = 0; i < numTriangles; i++) {
    const angle1 = (i / numTriangles) * 2 * Math.PI;
    const angle2 = ((i + 1) / numTriangles) * 2 * Math.PI;
    // Center point
    vertices.push(0, 1.5, 0);
    // First edge
    vertices.push(radius * Math.cos(angle1), 1.5, radius * Math.sin(angle1));
    // Second edge
    vertices.push(radius * Math.cos(angle2), 1.5, radius * Math.sin(angle2));
  }
  const vertexBuffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, vertexBuffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(vertices), gl.STATIC_DRAW);

  const vertSrc = `
    attribute vec3 position;
    void main() {
      gl_Position = vec4(position, 1.0);
    }
  `;
  const fragSrc = `
    precision mediump float;
    void main() {
      gl_FragColor = vec4(1.0, 0.0, 0.0, 1.0);
    }
  `;
  function compileShader(src: string, type: number) {
    const shader = gl.createShader(type)!;
    gl.shaderSource(shader, src);
    gl.compileShader(shader);
    return shader;
  }
  const vertShader = compileShader(vertSrc, gl.VERTEX_SHADER);
  const fragShader = compileShader(fragSrc, gl.FRAGMENT_SHADER);
  const program = gl.createProgram()!;
  gl.attachShader(program, vertShader);
  gl.attachShader(program, fragShader);
  gl.linkProgram(program);
  gl.useProgram(program);

  const posLoc = gl.getAttribLocation(program, 'position');
  gl.bindBuffer(gl.ARRAY_BUFFER, vertexBuffer);
  gl.enableVertexAttribArray(posLoc);
  gl.vertexAttribPointer(posLoc, 3, gl.FLOAT, false, 0, 0);

  gl.drawArrays(gl.TRIANGLES, 0, numTriangles * 3);

  gl.disableVertexAttribArray(posLoc);
  gl.deleteBuffer(vertexBuffer);
  gl.deleteProgram(program);
  gl.deleteShader(vertShader);
  gl.deleteShader(fragShader);
}
