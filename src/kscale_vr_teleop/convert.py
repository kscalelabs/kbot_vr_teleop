import json
import numpy as np

# Order of hand joints (must match your doc!)
JOINT_ORDER = [
    "wrist", "thumb-metacarpal", "thumb-phalanx-proximal", "thumb-phalanx-distal", "thumb-tip",
    "index-finger-metacarpal", "index-finger-phalanx-proximal", "index-finger-phalanx-intermediate", "index-finger-phalanx-distal", "index-finger-tip",
    "middle-finger-metacarpal", "middle-finger-phalanx-proximal", "middle-finger-phalanx-intermediate", "middle-finger-phalanx-distal", "middle-finger-tip",
    "ring-finger-metacarpal", "ring-finger-phalanx-proximal", "ring-finger-phalanx-intermediate", "ring-finger-phalanx-distal", "ring-finger-tip",
    "pinky-finger-metacarpal", "pinky-finger-phalanx-proximal", "pinky-finger-phalanx-intermediate", "pinky-finger-phalanx-distal", "pinky-finger-tip"
]

def make_matrix(position, orientation):
    """
    Build a 4x4 transform matrix from position + quaternion orientation.
    Stored in column-major order as required.
    """
    x, y, z = position["x"], position["y"], position["z"]
    qx, qy, qz, qw = orientation["x"], orientation["y"], orientation["z"], orientation["w"]

    # Quaternion to rotation matrix
    rot = np.array([
        [1 - 2*qy*qy - 2*qz*qz, 2*qx*qy - 2*qz*qw,     2*qx*qz + 2*qy*qw,     0],
        [2*qx*qy + 2*qz*qw,     1 - 2*qx*qx - 2*qz*qz, 2*qy*qz - 2*qx*qw,     0],
        [2*qx*qz - 2*qy*qw,     2*qy*qz + 2*qx*qw,     1 - 2*qx*qx - 2*qy*qy, 0],
        [0,                     0,                     0,                     1]
    ], dtype=np.float32)

    # Add translation
    rot[0, 3] = x
    rot[1, 3] = y
    rot[2, 3] = z

    # Flatten column-major
    return rot.T.flatten()

def convert_hand(hand_json):
    """
    Convert one hand's JSON into a Float32Array of 25*16 values.
    """
    matrices = []
    for joint in JOINT_ORDER:
        if joint in hand_json["joints"]:
            j = hand_json["joints"][joint]
            mat = make_matrix(j["position"], j["orientation"])
        else:
            mat = np.eye(4, dtype=np.float32).T.flatten()  # fallback identity
        matrices.append(mat)
    return np.concatenate(matrices).astype(np.float32)


def convert(data):
    """
    Takes raw JSON string from WebXR and converts it.
    """
    hands_out = {
        "left": None,
        "right": None,
        "leftState": {
            "pinch": False,
            "squeeze": False,
            "tap": False,
            "pinchValue": 0.0,
            "squeezeValue": 0.0,
            "tapValue": 0.0,
        },
        "rightState": {
            "pinch": False,
            "squeeze": False,
            "tap": False,
            "pinchValue": 0.0,
            "squeezeValue": 0.0,
            "tapValue": 0.0,
        }
    }

    for hand in ["left", "right"]:
        if hand in data["hands"]:
            hands_out[hand] = convert_hand(data["hands"][hand]).tolist()

    return hands_out

# ---------------- Example usage ----------------
if __name__ == "__main__":
    # Example incoming JSON (from your React/WebXR app)
    incoming = '''
    {
      "timestamp": 123456,
      "hands": {
        "left": {
          "joints": {
            "wrist": {
              "position": {"x": 0, "y": 0, "z": 0},
              "orientation": {"x": 0, "y": 0, "z": 0, "w": 1},
              "radius": 0.02
            }
          }
        }
      }
    }
    '''

    out = convert(incoming)
    print(json.dumps(out, indent=2))
