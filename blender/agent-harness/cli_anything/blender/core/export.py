"""Script generation and rendering for cli-anything-blender.

Generates bpy Python scripts from project JSON, then invokes Blender
headlessly to execute them and produce rendered output.
"""

import os
import tempfile
from pathlib import Path
from typing import Any

from cli_anything.blender.utils.blender_backend import run_script


def _color_from_value(value: float, min_val: float, max_val: float) -> tuple[float, float, float]:
    """Map a scalar value to an RGB color using a blue→red gradient (HSV).

    Args:
        value: The scalar value.
        min_val: Minimum value (maps to blue, hue=0.66).
        max_val: Maximum value (maps to red, hue=0.0).

    Returns:
        (r, g, b) tuple in [0, 1] range.
    """
    if max_val == min_val:
        return (0.0, 0.5, 1.0)
    t = (value - min_val) / (max_val - min_val)
    # HSV: hue goes from 0.66 (blue) to 0.0 (red)
    hue = 0.66 * (1.0 - t)
    # Simple HSV→RGB (S=1, V=1)
    h = hue * 6.0
    i = int(h) % 6
    f = h - int(h)
    q = 1.0 - f
    if i == 0:
        return (1.0, f, 0.0)
    elif i == 1:
        return (q, 1.0, 0.0)
    elif i == 2:
        return (0.0, 1.0, f)
    elif i == 3:
        return (0.0, q, 1.0)
    elif i == 4:
        return (f, 0.0, 1.0)
    else:
        return (1.0, 0.0, q)


def generate_scene_script(project: dict[str, Any], output_path: str) -> str:
    """Generate a bpy Python script that recreates the project scene.

    Args:
        project: Project dict (from core.project).
        output_path: Path where the rendered image will be saved.

    Returns:
        Python source code as a string.
    """
    scene = project.get("scene", {})
    render = project.get("render", {})
    objects = scene.get("objects", [])
    camera = scene.get("camera", {})
    lights = scene.get("lights", [])
    world = scene.get("world", {})

    lines = [
        "import bpy",
        "import math",
        "",
        "# ── Clear default scene ──────────────────────────────────────────────",
        "bpy.ops.object.select_all(action='SELECT')",
        "bpy.ops.object.delete(use_global=False)",
        "",
        "# ── World background ─────────────────────────────────────────────────",
    ]

    bg = world.get("background_color", [0.05, 0.05, 0.05, 1.0])
    lines += [
        "world = bpy.context.scene.world",
        "if world is None:",
        "    world = bpy.data.worlds.new('World')",
        "    bpy.context.scene.world = world",
        "world.use_nodes = True",
        "bg_node = world.node_tree.nodes.get('Background')",
        "if bg_node:",
        f"    bg_node.inputs[0].default_value = ({bg[0]}, {bg[1]}, {bg[2]}, {bg[3]})",
        f"    bg_node.inputs[1].default_value = 1.0",
        "",
    ]

    lines += [
        "# ── Lights ───────────────────────────────────────────────────────────",
    ]
    for i, light in enumerate(lights):
        ltype = light.get("type", "SUN")
        lloc = light.get("location", [5.0, 5.0, 10.0])
        energy = light.get("energy", 3.0)
        lines += [
            f"light_data_{i} = bpy.data.lights.new(name='Light_{i}', type='{ltype}')",
            f"light_data_{i}.energy = {energy}",
            f"light_obj_{i} = bpy.data.objects.new(name='Light_{i}', object_data=light_data_{i})",
            f"bpy.context.scene.collection.objects.link(light_obj_{i})",
            f"light_obj_{i}.location = ({lloc[0]}, {lloc[1]}, {lloc[2]})",
        ]
    lines.append("")

    lines += [
        "# ── Objects ──────────────────────────────────────────────────────────",
    ]
    for i, obj in enumerate(objects):
        otype = obj.get("type", "CUBE")
        oname = obj.get("name", f"Object_{i}")
        oloc = obj.get("location", [0.0, 0.0, 0.0])
        oscale = obj.get("scale", [1.0, 1.0, 1.0])
        ocolor = obj.get("color", [0.5, 0.5, 0.5, 1.0])

        if otype == "CUBE":
            lines.append(f"bpy.ops.mesh.primitive_cube_add(location=({oloc[0]}, {oloc[1]}, {oloc[2]}))")
        elif otype == "SPHERE":
            lines.append(f"bpy.ops.mesh.primitive_uv_sphere_add(location=({oloc[0]}, {oloc[1]}, {oloc[2]}))")
        elif otype == "PLANE":
            lines.append(f"bpy.ops.mesh.primitive_plane_add(location=({oloc[0]}, {oloc[1]}, {oloc[2]}))")
        elif otype == "CYLINDER":
            lines.append(f"bpy.ops.mesh.primitive_cylinder_add(location=({oloc[0]}, {oloc[1]}, {oloc[2]}))")
        else:
            lines.append(f"bpy.ops.mesh.primitive_cube_add(location=({oloc[0]}, {oloc[1]}, {oloc[2]}))")

        lines += [
            f"obj_{i} = bpy.context.active_object",
            f"obj_{i}.name = {oname!r}",
            f"obj_{i}.scale = ({oscale[0]}, {oscale[1]}, {oscale[2]})",
            f"mat_{i} = bpy.data.materials.new(name='Mat_{oname}')",
            f"mat_{i}.use_nodes = True",
            f"bsdf_{i} = mat_{i}.node_tree.nodes.get('Principled BSDF')",
            f"if bsdf_{i}: bsdf_{i}.inputs['Base Color'].default_value = ({ocolor[0]}, {ocolor[1]}, {ocolor[2]}, {ocolor[3]})",
            f"obj_{i}.data.materials.append(mat_{i})",
            "",
        ]

    cam_loc = camera.get("location", [0.0, -10.0, 5.0])
    cam_rot = camera.get("rotation_euler", [1.1, 0.0, 0.0])
    lines += [
        "# ── Camera ───────────────────────────────────────────────────────────",
        "cam_data = bpy.data.cameras.new('Camera')",
        "cam_obj = bpy.data.objects.new('Camera', cam_data)",
        "bpy.context.scene.collection.objects.link(cam_obj)",
        f"cam_obj.location = ({cam_loc[0]}, {cam_loc[1]}, {cam_loc[2]})",
        f"cam_obj.rotation_euler = ({cam_rot[0]}, {cam_rot[1]}, {cam_rot[2]})",
        "bpy.context.scene.camera = cam_obj",
        "",
    ]

    engine = render.get("engine", "EEVEE")
    res_x = render.get("resolution_x", 1920)
    res_y = render.get("resolution_y", 1080)
    samples = render.get("samples", 64)
    fmt = render.get("file_format", "PNG")

    lines += [
        "# ── Render settings ──────────────────────────────────────────────────",
        f"bpy.context.scene.render.engine = 'BLENDER_{engine}' if '{engine}' in ('EEVEE', 'WORKBENCH') else '{engine}'",
        f"bpy.context.scene.render.resolution_x = {res_x}",
        f"bpy.context.scene.render.resolution_y = {res_y}",
        f"bpy.context.scene.render.image_settings.file_format = '{fmt}'",
        f"bpy.context.scene.render.filepath = {output_path!r}",
        "",
        "if bpy.context.scene.render.engine == 'CYCLES':",
        f"    bpy.context.scene.cycles.samples = {samples}",
        "elif bpy.context.scene.render.engine == 'BLENDER_EEVEE':",
        f"    bpy.context.scene.eevee.taa_render_samples = {samples}",
        "",
        "# ── Render ───────────────────────────────────────────────────────────",
        "bpy.ops.render.render(write_still=True)",
        "print(f'Rendered to: {bpy.context.scene.render.filepath}')",
    ]

    return "\n".join(lines)


def render_project(
    project: dict[str, Any],
    output_path: str | None = None,
    timeout: int = 300,
) -> str:
    """Render a project to an image file.

    Args:
        project: Project dict.
        output_path: Path for the rendered image. Uses project's render.output_path
                     if not provided. Defaults to /tmp/blender_render.png.
        timeout: Max render time in seconds.

    Returns:
        Path to the rendered output file.

    Raises:
        RuntimeError: If rendering fails.
    """
    if output_path is None:
        output_path = project.get("render", {}).get("output_path", "")
    if not output_path:
        output_path = str(Path(tempfile.gettempdir()) / "blender_render.png")

    script = generate_scene_script(project, output_path)
    result = run_script(script, timeout=timeout)

    if result.returncode != 0:
        raise RuntimeError(
            f"Blender render failed (exit {result.returncode}):\n"
            f"STDOUT:\n{result.stdout[-2000:]}\n"
            f"STDERR:\n{result.stderr[-2000:]}"
        )

    return output_path
