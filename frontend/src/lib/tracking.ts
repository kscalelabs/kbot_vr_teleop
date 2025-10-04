// Shared WebXR hand and controller tracking logic
// Usage: import { handleHandTracking, handleControllerTracking } from './webxrTracking';
import { SceneState, LocalTargetLocation, TrackingResult, MasterResult, UnifiedTrackingResult } from './types';

/**
  Function that shifts the position in a transformation matrix along its forward direction.
  Used to align the tip of the controller/end-effector with the tip of the controllers 
  for a better teleoperation experience.
  
  @param matrix - 4x4 transformation matrix in column-major format (16 elements)
  @param offset - Distance to shift along forward direction (-Z axis)
  @returns Modified matrix with shifted position
*/
function shiftMatrixAlongForward(matrix: number[], offset: number): number[] {
  // Matrix is column-major: columns are [right, up, forward, position]
  // Forward vector is 3rd column (indices 8, 9, 10)
  // Position is 4th column (indices 12, 13, 14)
  
  const result = [...matrix];
  
  // Shift position by -forward * offset (negative because we want to move back along forward)
  result[12] = matrix[12] - matrix[8] * offset;  // X position
  result[13] = matrix[13] - matrix[9] * offset;  // Y position
  result[14] = matrix[14] - matrix[10] * offset; // Z position
  
  return result;
}

function handleHandTracking(frame, referenceSpace): UnifiedTrackingResult {  
  const result: UnifiedTrackingResult = { type: "hand", left: null, right: null };
  const JOINT_ORDER = [
    "thumb-metacarpal", "thumb-phalanx-proximal", "thumb-phalanx-distal", "thumb-tip",
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
      const handedness: 'right' | 'left' = inputSource.handedness;
      if (handedness === 'right' || handedness === 'left') {
        const hand = inputSource.hand;
        
        // Get wrist matrix for targetLocation
        const wristJoint = hand.get('wrist');
        let wristMatrix: number[] = [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]; // Identity default
        
        if (wristJoint && frame.getJointPose) {
          const wristPose = frame.getJointPose(wristJoint, referenceSpace);
          if (wristPose) {
            wristMatrix = Array.from(wristPose.transform.matrix);
          }
        }
        
        // Get all finger joints (24 joints)
        const fingerJoints: number[] = [];
        for (let i = 0; i < JOINT_ORDER.length; i++) {
          const jointName = JOINT_ORDER[i];
          const joint = hand.get(jointName);
          if (joint && frame.getJointPose) {
            const jointPose = frame.getJointPose(joint, referenceSpace);
            if (jointPose) {
              fingerJoints.push(...(Array.from(jointPose.transform.matrix) as number[]));
            } else {
              fingerJoints.push(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1);
            }
          } else {
            fingerJoints.push(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1);
          }
        }
        
        result[handedness] = {
          targetLocation: wristMatrix,  // 16 elements
          joints: fingerJoints           // 384 elements (24 joints × 16)
        };
      }
    }
  }

  return result;
}

function handleControllerTracking(frame, referenceSpace, joystickScale: number): UnifiedTrackingResult {  
  const result: UnifiedTrackingResult = { type: "controller", left: null, right: null };
  
  for (const inputSource of frame.session.inputSources) {
    if (inputSource.targetRayMode === 'tracked-pointer' && inputSource.gripSpace && !inputSource.hand) {
        const handedness: 'right' | 'left' = inputSource.handedness;
        if(handedness === 'right' || handedness === 'left'){
          const controllerPose = frame.getPose(inputSource.gripSpace, referenceSpace);
          
          if (controllerPose) {
            const gamepad = inputSource.gamepad;
            
            // Get matrix and shift position by 0.09 units along forward direction
            const matrix = Array.from(controllerPose.transform.matrix) as number[];
            const shiftedMatrix = shiftMatrixAlongForward(matrix, -0.09);
            
            result[handedness] = {
              targetLocation: shiftedMatrix, // 16 elements with shifted position
              joints: [],
              trigger: gamepad?.buttons[0]?.value || 0,
              grip: gamepad?.buttons[1]?.value || 0,
              joystickX: (gamepad?.axes[2] || 0) * joystickScale,
              joystickY: -(gamepad?.axes[3] || 0) * joystickScale,
              buttons: gamepad?.buttons.map(b => b.pressed) || []
            };
          }
      }
    }
  }
  return result;
}

export function handleTracking(frame, referenceSpace, wsRef, lastHandSendRef, pauseCommands, joystickScale): UnifiedTrackingResult | null {
  const now = performance.now();
  const sendInterval = 1000 / 40; // 40 Hz
  const shouldSend = now - lastHandSendRef.current >= sendInterval;
  
  if (shouldSend) {
    lastHandSendRef.current = now;
  }
  else{
    return null;
  }

  let response = handleHandTracking(frame, referenceSpace);
  if(response.left == null || response.right == null){
    response = handleControllerTracking(frame, referenceSpace, joystickScale);
  }
  if(pauseCommands){
    return response;
  }
  if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
    try {
      wsRef.current.send(JSON.stringify(response));
    } catch (error) {
      console.log(`Failed to send tracking data: ${error}`);
    }
  }
  return response;
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