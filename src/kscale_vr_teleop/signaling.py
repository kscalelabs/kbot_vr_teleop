import asyncio
import json
import websockets
from typing import Optional
import logging
from kscale_vr_teleop.tracking_handler import TrackingHandler
from kscale_vr_teleop._assets import ASSETS_DIR
from kscale_vr_teleop.jax_ik import RobotInverseKinematics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

tracking_handler = None
urdf_path  = str(ASSETS_DIR / "kbot_legless" / "robot.urdf")
ik_solver = RobotInverseKinematics(urdf_path, ['PRT0001', 'PRT0001_2'], 'base')

class SimpleConnection:
    def __init__(self):
        self.app_ws: Optional[websockets.WebSocketServerProtocol] = None
        self.robot_ws: Optional[websockets.WebSocketServerProtocol] = None
    
    async def relay_robot_message(self, message: str):
        """Relay message from robot to app"""
        if self.app_ws:
            try:
                await self.app_ws.send(message)
            except:
                logger.error("Failed to relay message from robot to app")
                self.app_ws = None

    async def relay_app_message(self, message: str):
        """Relay message from app to robot"""
        if self.robot_ws:
            try:
                await self.robot_ws.send(message)
            except:
                logger.error("Failed to relay message from app to robot")
                self.robot_ws = None

# Global single connection
connection = SimpleConnection()
connection_lock = asyncio.Lock()

async def handle_robot(websocket):
    """Handle robot connection"""    
    async with connection_lock:
        # If there's already a robot connected, disconnect the old one
        if connection.robot_ws and connection.robot_ws != websocket:
            logger.info(f"Replacing existing robot connection")
            try:
                await connection.robot_ws.close()
            except:
                pass
        
        connection.robot_ws = websocket
        
        # If app is already connected, notify it that robot is available
        if connection.app_ws:
            try:
                await connection.app_ws.send(json.dumps({"type": "info", "payload": "robot_available"}))
                logger.info("Notified app that robot is available")
            except:
                logger.error("Failed to notify app of robot availability")
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                await connection.relay_robot_message(message)
                    
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON from robot ")
                
    except websockets.ConnectionClosed:
        logger.info(f"Robot disconnected")
    finally:
        # Clean up robot connection
        async with connection_lock:
            if connection.robot_ws == websocket:
                if connection.app_ws:
                    try:
                        await connection.app_ws.send(json.dumps({"type": "error", "error": "Robot disconnected"}))
                    except:
                        pass
                logger.info("Cleaning up robot connection")
                connection.robot_ws = None

async def handle_app(websocket, robot_ip: str):
    """Handle app connection"""
    logger.info(f"App requesting connection to robot at {robot_ip}")
    
    async with connection_lock:
        # If there's already an app connected, disconnect the old one
        if connection.app_ws and connection.app_ws != websocket:
            logger.info(f"Replacing existing app connection")
            try:
                await connection.app_ws.close()
            except:
                pass
        
        connection.app_ws = websocket
        
        # Immediately connect to robot
        try:
            print(f"Connecting to robot at {robot_ip}:8765")
            robot_ws = await websockets.connect(f"ws://{robot_ip}:8765")
            connection.robot_ws = robot_ws
            logger.info(f"Connected to robot at {robot_ip}:8765")
            
            # Start handling robot messages in background
            asyncio.create_task(handle_robot(robot_ws))
            
        except Exception as e:
            logger.error(f"Failed to connect to robot at {robot_ip}:8765: {e}")
            await websocket.send(json.dumps({"type": "error", "error": f"Failed to connect to robot: {e}"}))
            return
    
    try:
        async for message in websocket:
            try:
                await connection.relay_app_message(message)
                    
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON from app")
                
    except websockets.ConnectionClosed:
        logger.info(f"App disconnected")
    finally:
        # Clean up app connection
        async with connection_lock:
            if connection.app_ws == websocket:
                if connection.robot_ws:
                    try:
                        await connection.robot_ws.send(json.dumps({"type": "connection_closed"}))
                        await connection.robot_ws.close()
                    except:
                        pass
                logger.info("Cleaning up app connection")
                connection.app_ws = None
                connection.robot_ws = None

async def handle_teleop(websocket):
    """Handle teleop connection - forwards messages over UDP"""
    global tracking_handler
    tracking_handler.teleop_core.reset_to_home()
    try:
        async for message in websocket:
            try:
                # Parse the incoming message
                data = json.loads(message)
                await tracking_handler.handle_tracking(data)

                logger.debug(f"Forwarded teleop message to UDP ")
                
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON from teleop client for robot")
                
    except websockets.ConnectionClosed:
        logger.info(f"Teleop client for robot disconnected")

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
        robot_ip = data.get("robot_ip")

        if role == "app":
            await handle_app(websocket, robot_ip)
        elif role == "teleop":
            tracking_handler = TrackingHandler(websocket, udp_host=robot_ip, ik_solver=ik_solver)
            await handle_teleop(websocket)
        else:
            await websocket.send(json.dumps({"type": "error", "error": "Invalid role"}))
            
    except websockets.ConnectionClosed:
        logger.info("Connection closed during handshake")
    except json.JSONDecodeError:
        logger.error("Invalid JSON in initial message")

async def main():
    server = await websockets.serve(handler, "0.0.0.0", 8013, ping_interval=10, ping_timeout=300)
    logger.info(f"Simple Robot-App signaling server running on ws://0.0.0.0:8013")
    logger.info("Supports one app and one robot connection")
    
    try:
        await server.wait_closed()
    except KeyboardInterrupt:
        logger.info("Server shutting down...")

if __name__ == "__main__":
    asyncio.run(main())
