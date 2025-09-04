#!/usr/bin/env python3
"""
Modified version of the URDF logger
"""
from __future__ import annotations

import argparse
import os
import pathlib
from typing import Optional

from PIL import Image
import numpy as np
import rerun as rr  # pip install rerun-sdk
import scipy.spatial.transform as st
import trimesh
from urdf_parser_py import urdf as urdf_parser
from pathlib import Path
from line_profiler import profile
from rerun.datatypes import RotationAxisAngle, Angle

class URDFLogger:
    """Class to log a URDF to Rerun."""

    def __init__(self, filepath: str, root_path: str = "") -> None:
        urdf_contents = open(filepath, 'r').read()
        urdf_parent_path =Path(filepath).absolute().parent
        urdf_contents = urdf_contents.replace('filename="', f'filename="{urdf_parent_path}/')
        self.urdf: urdf_parser.Robot = urdf_parser.URDF.from_xml_string(urdf_contents)
        self.mat_name_to_mat = {mat.name: mat for mat in self.urdf.materials}
        self.entity_to_transform = {}
        self.root_path = root_path
        self.meshes_cache = {}
        self.mesh_data_cache = {}
        self.joint_transform_set = set()
        rr.log(self.root_path + "", rr.ViewCoordinates.RIGHT_HAND_Z_UP, static=True)  # default ROS convention
    

    def link_entity_path(self, link: urdf_parser.Link) -> str:
        root_name = self.urdf.get_root()
        link_names = self.urdf.get_chain(root_name, link.name)[0::2]  # skip the joints
        return "/".join([n+'/link' for n in link_names])

    def joint_entity_path(self, joint: urdf_parser.Joint) -> str:
        return self.link_entity_path(self.urdf.link_map[joint.child])

    @profile
    def log(self, joint_angles: Optional[dict | list | tuple] = None) -> None:
        """Log the URDF to Rerun using an optional set of joint angles.

        joint_angles may be:
        - None: all joints default to 0.0
        - dict mapping joint name -> angle (radians for revolute/continuous, meters for prismatic)
        - list/tuple/ndarray providing angles in the same order as ``self.urdf.joints``
        """
        # Normalize joint_angles into a name->float map
        if joint_angles is None:
            joint_map = {}
        elif isinstance(joint_angles, (list, tuple, np.ndarray)):
            joint_map = {j.name: float(joint_angles[i]) if i < len(joint_angles) else 0.0 for i, j in enumerate(self.urdf.joints)}
        elif isinstance(joint_angles, dict):
            joint_map = {str(k): float(v) for k, v in joint_angles.items()}
        else:
            raise TypeError("joint_angles must be None, dict, or list/tuple/ndarray")


        for joint in self.urdf.joints:
            entity_path = self.joint_entity_path(joint)
            angle = float(joint_map.get(joint.name, 0.0))
            self.log_joint(entity_path, joint, angle)

        for link in self.urdf.links:
            entity_path = self.link_entity_path(link)
            self.log_link(entity_path, link)

    def log_link(self, entity_path: str, link: urdf_parser.Link) -> None:
        for i, visual in enumerate(link.visuals):
            self.log_visual(entity_path + f"/visual_{i}", visual)

    @profile
    def log_joint(self, entity_path: str, joint: urdf_parser.Joint, angle: float = 0.0) -> None:
        """Log a joint transform, applying the provided joint angle.

        For revolute/continuous joints the angle is interpreted as radians and a rotation
        about the joint axis is applied. For prismatic joints the angle is interpreted
        as a linear displacement along the joint axis (meters).
        """
        # Start from the joint origin (if present)

        if entity_path not in self.joint_transform_set:
            base_trans = np.zeros(3, dtype=float)
            base_rot = np.eye(3, dtype=float)

            if joint.origin is not None and joint.origin.xyz is not None:
                base_trans = np.array(joint.origin.xyz, dtype=float)

            if joint.origin is not None and joint.origin.rpy is not None:
                base_rot = st.Rotation.from_euler("xyz", joint.origin.rpy).as_matrix()

            origin_transform = np.eye(4, dtype=float)
            origin_transform[:3, :3] = base_rot
            origin_transform[:3, 3] = base_trans
            rr.log(self.root_path + entity_path[:-len('/link')], rr.Transform3D(translation=origin_transform[:3, 3], mat3x3=origin_transform[:3, :3]), static=True)
            joint_axis = joint.axis if joint.axis is not None else [1, 0, 0]
            rr.log(self.root_path + entity_path, rr.Transform3D(rotation_axis_angle=RotationAxisAngle(joint_axis, Angle(angle))))
            self.joint_transform_set.add(entity_path)
        else:
            joint_axis = joint.axis if joint.axis is not None else [1, 0, 0]
            rr.log(self.root_path + entity_path, rr.Transform3D.from_fields(quaternion=st.Rotation.from_rotvec(np.array(joint_axis) * angle).as_quat()))


    def load_mesh(self, path):
        if path not in self.mesh_data_cache:
            self.mesh_data_cache[path] = trimesh.load_mesh(path)
        return self.mesh_data_cache[path]

    @profile
    def log_visual(self, entity_path: str, visual: urdf_parser.Visual) -> None:
        if entity_path in self.meshes_cache:
            return
        material = None
        if visual.material is not None:
            if visual.material.color is None and visual.material.texture is None:
                material = self.mat_name_to_mat[visual.material.name]
            else:
                material = visual.material

        transform = np.eye(4)
        if visual.origin is not None and visual.origin.xyz is not None:
            transform[:3, 3] = visual.origin.xyz
        if visual.origin is not None and visual.origin.rpy is not None:
            transform[:3, :3] = st.Rotation.from_euler("xyz", visual.origin.rpy).as_matrix()

        if isinstance(visual.geometry, urdf_parser.Mesh):
            resolved_path = resolve_ros_path(visual.geometry.filename)
            mesh_scale = visual.geometry.scale
            mesh_or_scene = self.load_mesh(resolved_path)#
            if mesh_scale is not None:
                transform[:3, :3] *= mesh_scale
        elif isinstance(visual.geometry, urdf_parser.Box):
            mesh_or_scene = trimesh.creation.box(extents=visual.geometry.size)
        elif isinstance(visual.geometry, urdf_parser.Cylinder):
            mesh_or_scene = trimesh.creation.cylinder(
                radius=visual.geometry.radius,
                height=visual.geometry.length,
            )
        elif isinstance(visual.geometry, urdf_parser.Sphere):
            mesh_or_scene = trimesh.creation.icosphere(
                radius=visual.geometry.radius,
            )
        else:
            rr.log(self.root_path + 
                "",
                rr.TextLog("Unsupported geometry type: " + str(type(visual.geometry))),
            )
            mesh_or_scene = trimesh.Trimesh()
        
        if isinstance(mesh_or_scene, trimesh.Scene):
            scene = mesh_or_scene
            for i, mesh in enumerate(scene.dump()):
                if material is not None:
                    if material.color is not None:
                        mesh.visual = trimesh.visual.ColorVisuals()
                        mesh.visual.vertex_colors = material.color.rgba
                    elif material.texture is not None:
                        texture_path = resolve_ros_path(material.texture.filename)
                        mesh.visual = trimesh.visual.texture.TextureVisuals(image=Image.open(texture_path))
                log_trimesh(self.root_path + entity_path+f"/{i}", mesh)
        else:
            mesh = mesh_or_scene
            if material is not None:
                if material.color is not None:
                    mesh.visual = trimesh.visual.ColorVisuals()
                    mesh.visual.vertex_colors = material.color.rgba
                elif material.texture is not None:
                    texture_path = resolve_ros_path(material.texture.filename)
                    mesh.visual = trimesh.visual.texture.TextureVisuals(image=Image.open(texture_path))
            log_trimesh(self.root_path + entity_path, mesh)
        self.meshes_cache[entity_path] = mesh


@profile
def log_trimesh(entity_path: str, mesh: trimesh.Trimesh) -> None:
    vertex_colors = albedo_texture = vertex_texcoords = None
    if isinstance(mesh.visual, trimesh.visual.color.ColorVisuals):
        vertex_colors = mesh.visual.vertex_colors
    elif isinstance(mesh.visual, trimesh.visual.texture.TextureVisuals):
        albedo_texture = mesh.visual.material.baseColorTexture
        if len(np.asarray(albedo_texture).shape) == 2:
            albedo_texture = np.stack([albedo_texture] * 3, axis=-1)
        vertex_texcoords = mesh.visual.uv
        if vertex_texcoords is not None:
            vertex_texcoords[:, 1] = 1.0 - vertex_texcoords[:, 1]
    else:
        try:
            colors = mesh.visual.to_color().vertex_colors
            vertex_colors = colors
        except Exception:
            pass
    
    rr.log(
        entity_path,
        rr.Mesh3D(
            vertex_positions=mesh.vertices,
            triangle_indices=mesh.faces,
            vertex_normals=mesh.vertex_normals,
            vertex_colors=vertex_colors,
            albedo_texture=albedo_texture,
            vertex_texcoords=vertex_texcoords,
        ),
        static=True,
    )


def resolve_ros_path(path: str) -> str:
    if path.startswith("package://"):
        path = pathlib.Path(path)
        package_name = path.parts[1]
        relative_path = pathlib.Path(*path.parts[2:])

        package_path = resolve_ros1_package(package_name) or resolve_ros2_package(package_name)

        if package_path is None:
            raise ValueError(
                f"Could not resolve {path}."
                f"Replace with relative / absolute path, source the correct ROS environment, or install {package_name}."
            )

        return str(package_path / relative_path)
    elif str(path).startswith("file://"):
        return path[len("file://") :]
    else:
        return path


def resolve_ros2_package(package_name: str) -> Optional[str]:
    try:
        import ament_index_python

        try:
            return ament_index_python.get_package_share_directory(package_name)
        except ament_index_python.packages.PackageNotFoundError:
            return None
    except ImportError:
        return None


def resolve_ros1_package(package_name: str) -> str:
    try:
        import rospkg

        try:
            return rospkg.RosPack().get_path(package_name)
        except rospkg.ResourceNotFound:
            return None
    except ImportError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="""
This is an example executable data-loader plugin for the Rerun Viewer.
"""
    )
    parser.add_argument("filepath", type=str)
    parser.add_argument("--recording-id", type=str)
    args = parser.parse_args()

    is_file = os.path.isfile(args.filepath)
    is_urdf_file = ".urdf" in args.filepath

    if not is_file or not is_urdf_file:
        exit(rr.EXTERNAL_DATA_LOADER_INCOMPATIBLE_EXIT_CODE)

    rr.init("rerun_example_external_data_loader_urdf", recording_id=args.recording_id)
    rr.stdout()

    urdf_logger = URDFLogger(args.filepath)
    urdf_logger.log()


if __name__ == "__main__":
    main()
