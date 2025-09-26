import asyncio
import json
import websockets
import socket
from typing import Optional
import logging
from kscale_vr_teleop.tracking_handler import TrackingHandler
from kscale_vr_teleop._assets import ASSETS_DIR
from kscale_vr_teleop.analysis.rerun_loader_urdf import URDFLogger
from kscale_vr_teleop.jax_ik import RobotInverseKinematics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

tracking_handler = None
urdf_path  = str(ASSETS_DIR / "kbot_legless" / "robot.urdf")
urdf_logger = URDFLogger(urdf_path)
ik_solver = RobotInverseKinematics(urdf_path, ['PRT0001', 'PRT0001_2'], 'base')

class SimpleConnection:
    def __init__(self):
        self.app_ws: Optional[websockets.WebSocketServerProtocol] = None
        self.robot_ws: Optional[websockets.WebSocketServerProtocol] = None
        self.robot_id: Optional[str] = None
    
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

async def handle_robot(websocket, robot_id: str):
    """Handle robot connection"""
    logger.info(f"Robot {robot_id} connected")
    
    async with connection_lock:
        # If there's already a robot connected, disconnect the old one
        if connection.robot_ws and connection.robot_ws != websocket:
            logger.info(f"Replacing existing robot connection")
            try:
                await connection.robot_ws.close()
            except:
                pass
        
        connection.robot_ws = websocket
        connection.robot_id = robot_id
        
        # If app is already connected, notify it that robot is available
        if connection.app_ws:
            try:
                await connection.app_ws.send(json.dumps({"type": "robot_available"}))
                logger.info("Notified app that robot is available")
            except:
                logger.error("Failed to notify app of robot availability")
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                await connection.relay_robot_message(message)
                    
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON from robot {robot_id}")
                
    except websockets.ConnectionClosed:
        logger.info(f"Robot {robot_id} disconnected")
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
                connection.robot_id = None

async def handle_app(websocket, robot_id: str):
    """Handle app connection"""
    logger.info(f"App requesting connection")
    
    async with connection_lock:
        # If there's already an app connected, disconnect the old one
        if connection.app_ws and connection.app_ws != websocket:
            logger.info(f"Replacing existing app connection")
            try:
                await connection.app_ws.close()
            except:
                pass
        
        connection.app_ws = websocket
        
        # If robot is already connected, notify app immediately
        if connection.robot_ws:
            try:
                await websocket.send(json.dumps({"type": "robot_available"}))
                logger.info("App connected and robot is already available")
            except:
                logger.error("Failed to notify app of robot availability")
        else:
            logger.info("App connected, waiting for robot")
    
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
                    except:
                        pass
                logger.info("Cleaning up app connection")
                connection.app_ws = None

async def handle_teleop(websocket, robot_id: str):
    """Handle teleop connection - forwards messages over UDP"""
    global tracking_handler
    
    try:
        async for message in websocket:
            try:
                # Parse the incoming message
                data = json.loads(message)
                await tracking_handler.handle_hand_tracking(data)

                logger.debug(f"Forwarded teleop message to UDP: {robot_id}")
                
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON from teleop client for robot {robot_id}")
                
    except websockets.ConnectionClosed:
        logger.info(f"Teleop client for robot {robot_id} disconnected")

def get_ipv4_address():
    """Get the local IPv4 address of this machine"""
    try:
        # Connect to a remote address (doesn't actually send data)
        # This helps determine which local IP would be used for external connections
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        return local_ip
    except Exception as e:
        return f"Error getting IP address: {e}"

async def handler(websocket):
    ip = get_ipv4_address()
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.setblocking(False)

    # Increase send buffer size to handle bursts
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)  # 64KB

    # Set socket priority (if supported)
    try:
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_PRIORITY, 6)  # High priority
    except:
        pass  # Not all systems support this
    # Enable broadcast (useful for some network setups)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    
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
        udp_host = data.get("udp_host")

        # Send server IP to client via UDP if udp_host is provided
        if type(udp_host) == str:
            udp_sock.sendto(json.dumps({'ip': ip}).encode("utf-8"), (udp_host, 10002))
            logger.info(f"Sent server IP {ip} to {udp_host}:10002")

        if role == "robot":
            await handle_robot(websocket, robot_id)
        elif role == "app":
            await handle_app(websocket, robot_id)
        elif role == "teleop":
            tracking_handler = TrackingHandler(websocket, udp_host=udp_host, urdf_logger=urdf_logger, ik_solver=ik_solver)
            await handle_teleop(websocket, robot_id)
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
