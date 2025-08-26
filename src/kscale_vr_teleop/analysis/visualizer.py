import numpy as np
import time
import threading
from queue import Queue, Empty
from yourdfpy import URDF
import trimesh

# Method 1: Threading approach - run viewer in separate thread
class ThreadedRobotVisualizer:
    def __init__(self, make_robot):
        self.robot: URDF = make_robot()
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

    def _create_axis_marker(self, length=0.08, radius=0.003):
        """Create a coordinate axis marker (X=red, Y=green, Z=blue)"""
        x_cylinder = trimesh.creation.cylinder(radius=radius, height=length, sections=8)
        x_cylinder.apply_transform(
            trimesh.transformations.rotation_matrix(np.pi/2, [0, 1, 0])
        )
        x_cylinder.visual.face_colors = [255, 0, 0, 255]
        
        y_cylinder = trimesh.creation.cylinder(radius=radius, height=length, sections=8)
        y_cylinder.apply_transform(
            trimesh.transformations.rotation_matrix(-np.pi/2, [1, 0, 0])
        )
        y_cylinder.visual.face_colors = [0, 255, 0, 255]
        
        z_cylinder = trimesh.creation.cylinder(radius=radius, height=length, sections=8)
        z_cylinder.visual.face_colors = [0, 0, 255, 255]
        
        return [x_cylinder, y_cylinder, z_cylinder]

    def _get_marker_geom_names(self, marker_name):
        """Get all geometry names for a marker"""
        return [f"{marker_name}_{suffix}" for suffix in 
                ['x_axis', 'y_axis', 'z_axis', 'x_arrow', 'y_arrow', 'z_arrow']]

    def _remove_marker_geometries(self, marker_name):
        """Remove all geometries associated with a marker"""
        geom_names = self._get_marker_geom_names(marker_name)
        for geom_name in geom_names:
            if geom_name in self.robot.scene.geometry:
                del self.robot.scene.geometry[geom_name]
            if geom_name in self.robot.scene.graph.nodes:
                self.robot.scene.graph.remove_node(geom_name)

    def add_marker(self, name, position, orientation=None, size=0.08):
        transform = np.eye(4)
        transform[:3, 3] = position
        if orientation is not None:
            transform[:3, :3] = orientation
        
        self._remove_marker_geometries(name)
        
        geometries = self._create_axis_marker(length=size, radius=size * 0.04)
        geom_names = self._get_marker_geom_names(name)
        
        for geom, geom_name in zip(geometries, geom_names):
            self.robot.scene.add_geometry(
                geometry=geom,
                geom_name=geom_name,
                transform=transform
            )

    def update_marker(self, name, position, orientation=None):
        transform = np.eye(4)
        transform[:3, 3] = position
        if orientation is not None:
            transform[:3, :3] = orientation
        
        geom_names = self._get_marker_geom_names(name)
        
        if not any(geom_name in self.robot.scene.geometry for geom_name in geom_names):
            print(f"Warning: Marker '{name}' does not exist. Use add_marker() first.")
            return
        
        for geom_name in geom_names:
            if geom_name in self.robot.scene.geometry:
                for node_name in self.robot.scene.graph.nodes_geometry:
                    if self.robot.scene.graph.geometry_nodes[node_name][0] == geom_name:
                        self.robot.scene.graph.update(
                            frame_from=self.robot.base_link,
                            frame_to=node_name,
                            matrix=transform
                        )
