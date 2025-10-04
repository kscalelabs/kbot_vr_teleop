import * as THREE from 'three';

// WebSocket message types
export interface ForwardKinematicsMessage {
  type: "kinematics";
  joints: {
    right: number[];
    left: number[];
  };
  distances: {
    right: number;
    left: number;
  };
}

export interface AppConnectionMessage {
  role: "app";
  robot_ip: string;
}

// Tracking types
export type LocalTargetLocation = {
  left: {
    position: number[];
    orientation: number[];

  } | null;
  right: {
    position: number[];
    orientation: number[];
  } | null;
};

export type TrackingResult = {
  type: "hand" | "controller";
  handPositions: LocalTargetLocation;
  payload: any;
};

export type UnifiedTrackingResult = {
  type: "hand" | "controller";
  right: MasterResult | null
  left: MasterResult | null
};

export type MasterResult = {
  targetLocation: number[]
  joints: number[]
  joystickX?: number
  joystickY?: number
  trigger?: number
  grip?: number
  buttons?: boolean[]
}
// Three.js scene state
export type SceneState = {
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
  joystickScale: number;
  previousButtonStates: Map<string, boolean>;
  lastLeftColorRef: number;
  lastRightColorRef: number;
};

export const DEFAULT_SCENE_STATE: SceneState = {
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
  joystickScale: 0.1,
  previousButtonStates: new Map<string, boolean>(),
  lastLeftColorRef: -1,
  lastRightColorRef: -1
};

// webRTC types
export interface SignalingMessage {
    type: "sdp" | "ice" | "info";
    sdp?: RTCSessionDescriptionInit;
    ice?: {
      candidate: string;
      sdpMLineIndex: number | null;
    };
    payload?: string
  }
  
  export interface WebRtcInitializationMessage {
    type: "HELLO";
    cameras: number[];
    audio: boolean;
  }