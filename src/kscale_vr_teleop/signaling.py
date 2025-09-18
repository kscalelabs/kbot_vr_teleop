import asyncio
import json
import websockets
import os
import argparse
import logging
from typing import Optional
from kscale_vr_teleop.tracking_handler import TrackingHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SignalingClient:
    def __init__(self, uri: str, robot_id: str = "box"):
        self.uri = uri
        self.robot_id = robot_id
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.tracking_handler: Optional[TrackingHandler] = None

    async def connect(self):
        logger.info(f"Connecting to signaling server at {self.uri}")
        async with websockets.connect(self.uri) as websocket:
            self.ws = websocket
            # send HELLO to start pipeline on robot server
            await websocket.send(json.dumps({"role": "app", "robot_id": self.robot_id}))
            await websocket.send(json.dumps({"type": "HELLO", "cameras": [0]}))

            async for message in websocket:
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    logger.error("Received non-JSON from server")
                    continue

                # If it's an SDP offer from robot, send answer via webrtc handled elsewhere (e.g., browser)
                # For now, just log and if teleop messages, forward to tracking handler
                if data.get("type") == "teleop":
                    if not self.tracking_handler:
                        self.tracking_handler = TrackingHandler(websocket=None, udp_host=os.environ.get("ROBOT_IP", "10.33.13.254"))
                    await self.tracking_handler.handle_hand_tracking(data)
                else:
                    logger.info(f"Signaling message: {data}")


async def main():
    parser = argparse.ArgumentParser(description='Signaling client connecting to robot')
    parser.add_argument('--host', default=os.environ.get('HOST_IP', '10.33.13.51'), help='Robot host/IP')
    parser.add_argument('--port', type=int, default=8013, help='Robot signaling port')
    parser.add_argument('--robot-id', default='box', help='Robot ID to connect to')
    args = parser.parse_args()

    uri = f"ws://{args.host}:{args.port}"
    client = SignalingClient(uri, robot_id=args.robot_id)
    await client.connect()


if __name__ == "__main__":
    asyncio.run(main())