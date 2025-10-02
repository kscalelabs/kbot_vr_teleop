// Shared WebXR hand and controller tracking logic
// Usage: import { handleHandTracking, handleControllerTracking } from './webxrTracking';
import React from 'react';
import { SceneState, LocalTargetLocation, TrackingResult } from './types';

/**
  Function that shifts the controllers position in the opposite direction of its
  orientation. Used to align the tip of the controller/end-effector with the
  tip of the controllers for a better teleoperation experience.
*/
function shiftTargetWithOrientation(pos, ori, offset) {

  const rotateVectorByQuaternion = (v, q) => {
    const vx = v.x, vy = v.y, vz = v.z;
    const qx = q.x, qy = q.y, qz = q.z, qw = q.w;
    const ix =  qw * vx + qy * vz - qz * vy;
    const iy =  qw * vy + qz * vx - qx * vz;
    const iz =  qw * vz + qx * vy - qy * vx;
    const iw = -qx * vx - qy * vy - qz * vz;
    return {
      x: ix * qw + iw * -qx + iy * -qz - iz * -qy,
      y: iy * qw + iw * -qy + iz * -qx - ix * -qz,
      z: iz * qw + iw * -qz + ix * -qy - iy * -qx,
    };
  };

  const forward = rotateVectorByQuaternion({ x: 0, y: 0, z: -1 }, ori);
  return [
    pos.x - forward.x * offset,
    pos.y - forward.y * offset,
    pos.z - forward.z * offset,
  ]
}

function handleHandTracking(frame, referenceSpace): TrackingResult {  
  const handData = {};
  const handPositions: LocalTargetLocation = { left: null, right: null };
  const JOINT_ORDER = [
    "wrist", "thumb-metacarpal", "thumb-phalanx-proximal", "thumb-phalanx-distal", "thumb-tip",
    "index-finger-metacarpal", "index-finger-phalanx-proximal", "index-finger-phalanx-intermediate", 
    "index-finger-phalanx-distal", "index-finger-tip", "middle-finger-metacarpal", 
    "middle-finger-phalanx-proximal", "middle-finger-phalanx-intermediate", "middle-finger-phalanx-distal",
    "middle-finger-tip", "ring-finger-metacarpal", "ring-finger-phalanx-proximal", 
    "ring-finger-phalanx-intermediate", "ring-finger-phalanx-distal", "ring-finger-tip",
    "pinky-finger-metacarpal", "pinky-finger-phalanx-proximal", "pinky-finger-phalanx-intermediate",
    "pinky-finger-phalanx-distal", "pinky-finger-tip"
  ];
  for (const inputSource of frame.session.inputSources) {
    if (inputSource.hand) {
      const handedness = inputSource.handedness;
      const hand = inputSource.hand;
      const continuousArray = [];
      
      // Extract wrist position for STL rendering
      const wristJoint = hand.get('wrist');
      if (wristJoint && frame.getJointPose) {
        const wristPose = frame.getJointPose(wristJoint, referenceSpace);
        if (wristPose) {
          const ori = wristPose.transform.orientation;
          const orientation = [
            ori.x,
            ori.y,
            ori.z,
            ori.w
          ];
          const pos = wristPose.transform.position;
          const posititon = [
            pos.x,
            pos.y,
            pos.z
          ]
          handPositions[handedness] = {
            position: posititon,
            orientation: orientation
          };
        }
      }
      
      for (let i = 0; i < JOINT_ORDER.length; i++) {
        const jointName = JOINT_ORDER[i];
        const joint = hand.get(jointName);
        if (joint && frame.getJointPose) {
          const jointPose = frame.getJointPose(joint, referenceSpace);
          if (jointPose) {
            continuousArray.push(...Array.from(jointPose.transform.matrix));
          } else {
            continuousArray.push(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1);
          }
        } else {
          continuousArray.push(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1);
        }
      }
      handData[handedness] = continuousArray;
    }
  }

  return { type: "hand", handPositions: handPositions, payload: handData };
}

function handleControllerTracking(frame, referenceSpace, joystickScale: number): TrackingResult {  
  const controllerData: LocalTargetLocation = { left: null, right: null };  
  for (const inputSource of frame.session.inputSources) {
    if (inputSource.targetRayMode === 'tracked-pointer' && inputSource.gripSpace && !inputSource.hand) {
      const handedness = inputSource.handedness;
      const controllerPose = frame.getPose(inputSource.gripSpace, referenceSpace);
      if (controllerPose) {
        // Offset position 0.5 units opposite controller forward direction
        const pos = controllerPose.transform.position;
        const ori = controllerPose.transform.orientation;
        const position = shiftTargetWithOrientation(pos, ori, 0.09);
        
        const orientation = [
          ori.x,
          ori.y,
          ori.z,
          ori.w
        ];
        
        const gamepad = inputSource.gamepad;
        let trigger = 0.0;
        let grip = 0.0;
        let buttons = [];
        let joystickX = 0.0;
        let joystickY = 0.0;
        if (gamepad) {
          trigger = gamepad.buttons[0]?.value || 0.0;
          grip = gamepad.buttons[1]?.value || 0.0;
          buttons = gamepad.buttons.map(button => button.pressed);
          // Joystick axes: typically axes[2] = x, axes[3] = y
          // Center is 0,0 with range from -1 to 1
          joystickX = gamepad.axes[2] || 0.0;
          joystickY = -1 * (gamepad.axes[3] || 0.0);
        }
        controllerData[handedness] = {
          position,
          orientation,
          trigger,
          grip,
          buttons,
          joystickX: joystickX * joystickScale,
          joystickY: joystickY * joystickScale,
        };
      }
    }
  }

  return { type: "controller", handPositions: controllerData, payload: controllerData };
}

export function handleTracking(frame, referenceSpace, wsRef, lastHandSendRef, pauseCommands, joystickScale): TrackingResult | null {
  const now = performance.now();
  const sendInterval = 1000 / 40; // 0 Hz
  const shouldSend = now - lastHandSendRef.current >= sendInterval;
  
  if (shouldSend) {
    lastHandSendRef.current = now;
  }
  else{
    return null;
  }

  let respone = handleHandTracking(frame, referenceSpace);
  if(respone.handPositions.left == null || respone.handPositions.right == null){
    respone = handleControllerTracking(frame, referenceSpace, joystickScale);
  }
  if(pauseCommands){
    return respone;
  }
  if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN && Object.keys(respone.payload).length > 0) {
    try {
      wsRef.current.send(JSON.stringify(respone.payload));
    } catch (error) {
      console.log(`Failed to send controller tracking data: ${error}`);
    }
  }
  return respone;
}

// Handle controller input for pause toggle and joystick scale
export const handleControllerInput = (frame: any, referenceSpace: any, sceneState: SceneState) => {
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
        const previousPressed = sceneState.previousButtonStates.get(stateKey) || false;

        // Only trigger on button press (not hold)
        if (currentPressed && !previousPressed) {
          sceneState.pauseCommands = !sceneState.pauseCommands;
        }

        // Update previous state
        sceneState.previousButtonStates.set(stateKey, currentPressed);
      }

    }

    // Right controller A and B buttons for joystick scale adjustment
    if (hand === 'right' && gamepad.buttons) {
      // Button 4 = A button, Button 5 = B button on Quest controllers
      
      // A button - decrease joystick scale
      if (gamepad.buttons[4]) {
        const currentPressed = gamepad.buttons[4].pressed;
        const stateKey = `${controllerKey}-a`;
        const previousPressed = sceneState.previousButtonStates.get(stateKey) || false;

        if (currentPressed && !previousPressed) {
          sceneState.joystickScale = Math.max(0.0, sceneState.joystickScale - 0.05);
        }

        sceneState.previousButtonStates.set(stateKey, currentPressed);
      }

      // B button - increase joystick scale
      if (gamepad.buttons[5]) {
        const currentPressed = gamepad.buttons[5].pressed;
        const stateKey = `${controllerKey}-b`;
        const previousPressed = sceneState.previousButtonStates.get(stateKey) || false;

        if (currentPressed && !previousPressed) {
          sceneState.joystickScale += 0.05;
        }

        sceneState.previousButtonStates.set(stateKey, currentPressed);
      }
    }
  }
};