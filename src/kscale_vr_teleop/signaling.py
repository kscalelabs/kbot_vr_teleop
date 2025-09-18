import asyncio
import json
import websockets
import socket
import time
import os
import argparse
from typing import Dict, Optional
import logging
from kscale_vr_teleop.tracking_handler import TrackingHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

tracking_handler = None


class RobotAppPair:
    def __init__(self, robot_id: str, robot_ws):
        self.robot_id = robot_id
        self.robot_ws = robot_ws
        self.app_ws: Optional[websockets.WebSocketServerProtocol] = None
    
    async def relay_robot_message(self, message: str):
        """Relay message from robot to app"""
        try:
            await self.app_ws.send(message)
        except:
            logger.error(f"Failed to relay message from robot to app {self.robot_id}")
            self.app_ws = None

    async def relay_app_message(self, message: str):
        """Relay message from app to robot"""
        try:
            await self.robot_ws.send(message)
        except:
            logger.error(f"Failed to relay message from app to robot {self.robot_id}")
            self.robot_ws = None

# Global storage for robot-app pairs
pairs: Dict[str, RobotAppPair] = {}
pairs_lock = asyncio.Lock()

# Global UDP handler for teleop messages

async def handle_robot(websocket, robot_id: str):
    """Handle robot connection"""
    logger.info(f"Robot {robot_id} connected")
    
    # Create or update the pair
    async with pairs_lock:
        pairs[robot_id] = RobotAppPair(robot_id, websocket)
        current_pair = pairs[robot_id]
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                # logger.info(f"Robot message: {data}")
                await current_pair.relay_robot_message(message)
                    
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON from robot {robot_id}")
                
    except websockets.ConnectionClosed:
        logger.info(f"Robot {robot_id} disconnected")
    finally:
        # Clean up
        async with pairs_lock:
            for key, pair in pairs.items():
                if key == robot_id:
                    if pair.app_ws != None:
                        await pair.app_ws.send(json.dumps({"type": "error", "error": "Robot disconnected"}))
                    logger.info(f"Cleaning up robot connection from pair {robot_id}")
                    del pairs[robot_id]

async def handle_app(websocket, robot_id: str):
    """Handle app connection"""
    logger.info(f"App requesting connection to robot {robot_id}")
    async with pairs_lock:
        pair = pairs.get(robot_id)
        if not pair:
            await websocket.send(json.dumps({"type": "error", "error": "Robot is not available"}))
            return
        # if  pair.app_ws != None:
        #     pair.app_ws = None
            # logger.info(f"Robot {robot_id} connected to different client")
            # await websocket.send(json.dumps({"type": "error", "error": "Robot connected to different app"}))

        pair.app_ws = websocket
        logger.info(f"App connected to robot {robot_id}")
        await websocket.send(json.dumps({"type": "robot_available"}))
    
    # Wait for password attempt from app
    try:
        async for message in websocket:
            try:
                # logger.info(f"App message: {data}")
                await pair.relay_app_message(message)
                    
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON from app connecting to robot {robot_id}")
                
    except websockets.ConnectionClosed:
        logger.info(f"App disconnected from robot {robot_id}")
    finally:
        # Clean up app connection from pair
        if pair and pair.app_ws == websocket:
            await pair.robot_ws.send(json.dumps({"type": "connection_closed"}))
            logger.info(f"Cleaning up app connection from pair")
            pair.app_ws = None

async def handle_teleop(websocket, robot_id: str):
    """Handle teleop connection - forwards messages over UDP"""
    
    # Send initial confirmation to teleop client  
    try:
        async for message in websocket:
            try:
                # Parse the incoming message
                data = json.loads(message)
                # Process through appropriate tracking handler
                await tracking_handler.handle_hand_tracking(data)

                logger.debug(f"Forwarded teleop message to UDP: {robot_id}")
                
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON from teleop client for robot {robot_id}")
            # except Exception as e:
            #     logger.error(f"Error processing teleop message for robot {robot_id}: {e}")
                
    except websockets.ConnectionClosed:
        logger.info(f"Teleop client for robot {robot_id} disconnected")
    # except Exception as e:
    #     logger.error(f"Error in teleop handler for robot {robot_id}: {e}")

async def handler(websocket):
    """Route connections based on role"""
    try:
        global tracking_handler
        # Wait for initial message to determine role
        logger.info(f"New connection, Waiting for initial message")
        initial_msg = await websocket.recv()
        data = json.loads(initial_msg)
        logger.info(f"Initial message: {data}")
        role = data.get("role")
        robot_id = data.get("robot_id")
        
        # if not robot_id:
        #     await websocket.send(json.dumps({"error": "robot_id required"}))
            # return
        if role == "robot":
            await handle_robot(websocket, robot_id)
        elif role == "app":
            await handle_app(websocket, robot_id)
        # elif role == "app":
        #     await handle_app(websocket, robot_id, False)
        elif role == "teleop":
            tracking_handler = TrackingHandler(websocket, udp_host=os.environ.get("ROBOT_IP", "10.33.13.254"))
            await handle_teleop(websocket, robot_id)
        else:
            websocket.send(json.dumps({"type": "error", "error": "Invalid role"}))
            
    except websockets.ConnectionClosed:
        logger.info("Connection closed during handshake")
    except json.JSONDecodeError:
        logger.error("Invalid JSON in initial message")
    # except Exception as e:
    #     logger.error(f"Error in handler: {e}")

async def main():
    
    server = await websockets.serve(handler, "0.0.0.0", 8013, ping_interval=10,   # send a ping every 20s
    ping_timeout=300 )
    logger.info(f"Robot-App signaling server running on ws://0.0.0.0:8013")
    
    try:
        await server.wait_closed()
    except KeyboardInterrupt:
        logger.info("Server shutting down...")

if __name__ == "__main__":
    asyncio.run(main())