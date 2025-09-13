// Shared WebXR hand and controller tracking logic
// Usage: import { handleHandTracking, handleControllerTracking } from './webxrTracking';

export function handleHandTracking(frame, referenceSpace, wsRef, lastHandSendRef) {
  const now = performance.now();
  const sendInterval = 1000 / 30; // 30 Hz
  const shouldSend = now - lastHandSendRef.current >= sendInterval;
  
  if (shouldSend) {
    lastHandSendRef.current = now;
  }
  
  const handData = {};
  const handPositions = { left: null, right: null };
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
          handPositions[handedness] = {
            position: wristPose.transform.position,
            orientation: wristPose.transform.orientation
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
  // Send WebSocket data only at specified interval
  if (shouldSend && wsRef.current && wsRef.current.readyState === WebSocket.OPEN && Object.keys(handData).length > 0) {
    try {
      wsRef.current.send(JSON.stringify(handData));
    } catch (error) {
      console.log(`Failed to send hand tracking data: ${error}`);
    }
  }
  
  // Always return hand positions for local rendering
  return handPositions;
}

export function handleControllerTracking(frame, referenceSpace, wsRef, lastHandSendRef) {
  const now = performance.now();
  const sendInterval = 1000 / 30; // 30 Hz
  const shouldSend = now - lastHandSendRef.current >= sendInterval;
  
  if (shouldSend) {
    lastHandSendRef.current = now;
  }
  
  const controllerData = {};
  const controllerPositions = { left: null, right: null };
  
  for (const inputSource of frame.session.inputSources) {
    if (inputSource.targetRayMode === 'tracked-pointer' && inputSource.gripSpace && !inputSource.hand) {
      const handedness = inputSource.handedness;
      const controllerPose = frame.getPose(inputSource.gripSpace, referenceSpace);
      if (controllerPose) {
        // Extract controller position for STL rendering
        controllerPositions[handedness] = {
          position: controllerPose.transform.position,
          orientation: controllerPose.transform.orientation
        };
        
        const position = [
          controllerPose.transform.position.x,
          controllerPose.transform.position.y,
          controllerPose.transform.position.z
        ];
        const orientation = [
          controllerPose.transform.orientation.x,
          controllerPose.transform.orientation.y,
          controllerPose.transform.orientation.z,
          controllerPose.transform.orientation.w
        ];
        const gamepad = inputSource.gamepad;
        let trigger = 0.0;
        let grip = 0.0;
        let buttons = [];
        if (gamepad) {
          trigger = gamepad.buttons[0]?.value || 0.0;
          grip = gamepad.buttons[1]?.value || 0.0;
          buttons = gamepad.buttons.map(button => button.pressed);
        }
        controllerData[handedness] = {
          position,
          orientation,
          trigger,
          grip,
          buttons
        };
      }
    }
  }
  
  // Send WebSocket data only at specified interval
  if (shouldSend && wsRef.current && wsRef.current.readyState === WebSocket.OPEN && Object.keys(controllerData).length > 0) {
    try {
      wsRef.current.send(JSON.stringify(controllerData));
    } catch (error) {
      console.log(`Failed to send controller tracking data: ${error}`);
    }
  }
  
  // Always return controller positions for local rendering
  return controllerPositions;
}
