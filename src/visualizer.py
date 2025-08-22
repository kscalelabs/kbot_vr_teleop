import numpy as np
import time
import threading
from queue import Queue, Empty
from yourdfpy import URDF
import trimesh

# Method 1: Threading approach - run viewer in separate thread
class ThreadedRobotVisualizer:
    def __init__(self, robot):
        self.robot = robot        
        self.config_queue = Queue()
        self.viewer_thread = None
        self.running = False
    
    def start_viewer(self):
        """Start the viewer in a separate thread"""
        self.running = True
        self.viewer_thread = threading.Thread(target=self._viewer_loop)
        self.viewer_thread.daemon = True
        self.viewer_thread.start()
    
    def _viewer_loop(self):
        """Internal viewer loop that runs in separate thread"""
        def callback(scene):
            # Check for new configurations from main thread
            try:
                while True:  # Process all queued updates
                    new_config = self.config_queue.get_nowait()
                    self.robot.update_cfg(new_config)
                    time.sleep(1/20)
            except Empty:
                pass  # No new updates
        
        # Start the viewer with callback
        self.robot.show(callback=callback)
    
    def update_config(self, config):
        """Update robot configuration from main thread"""
        if self.running:
            # Clear old updates and add new one
            while not self.config_queue.empty():
                try:
                    self.config_queue.get_nowait()
                except Empty:
                    break
            self.config_queue.put(config)
    
    def stop(self):
        """Stop the visualization"""
        self.running = False
        if self.viewer_thread and self.viewer_thread.is_alive():
            self.viewer_thread.join(timeout=1.0)