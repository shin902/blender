"""Scene management helpers for cli-anything-blender."""

from typing import Any

from cli_anything.blender.core.project import (
    add_object,
    remove_object,
    set_camera,
    get_object,
    list_objects,
)


VALID_OBJECT_TYPES = {"CUBE", "SPHERE", "PLANE", "CYLINDER", "CONE", "TORUS", "EMPTY"}
VALID_LIGHT_TYPES = {"SUN", "POINT", "SPOT", "AREA"}
VALID_ENGINES = {"EEVEE", "CYCLES", "WORKBENCH"}


def add_cube(
    project: dict[str, Any],
    name: str,
    location: list[float] | None = None,
    scale: list[float] | None = None,
    color: list[float] | None = None,
) -> dict[str, Any]:
    """Add a cube to the scene."""
    return add_object(project, {
        "type": "CUBE",
        "name": name,
        "location": location or [0.0, 0.0, 0.0],
        "scale": scale or [1.0, 1.0, 1.0],
        "color": color or [0.8, 0.8, 0.8, 1.0],
    })


def add_sphere(
    project: dict[str, Any],
    name: str,
    location: list[float] | None = None,
    scale: list[float] | None = None,
    color: list[float] | None = None,
) -> dict[str, Any]:
    """Add a UV sphere to the scene."""
    return add_object(project, {
        "type": "SPHERE",
        "name": name,
        "location": location or [0.0, 0.0, 0.0],
        "scale": scale or [1.0, 1.0, 1.0],
        "color": color or [0.8, 0.2, 0.2, 1.0],
    })


def add_plane(
    project: dict[str, Any],
    name: str,
    location: list[float] | None = None,
    scale: list[float] | None = None,
    color: list[float] | None = None,
) -> dict[str, Any]:
    """Add a plane to the scene."""
    return add_object(project, {
        "type": "PLANE",
        "name": name,
        "location": location or [0.0, 0.0, 0.0],
        "scale": scale or [1.0, 1.0, 1.0],
        "color": color or [0.3, 0.5, 0.3, 1.0],
    })


def move_object(
    project: dict[str, Any],
    name: str,
    location: list[float],
) -> dict[str, Any]:
    """Move an object to a new location.

    Raises:
        KeyError: If object not found.
    """
    obj = get_object(project, name)
    if obj is None:
        raise KeyError(f"Object not found: {name!r}")
    obj["location"] = location
    return project


def scale_object(
    project: dict[str, Any],
    name: str,
    scale: list[float],
) -> dict[str, Any]:
    """Scale an object.

    Raises:
        KeyError: If object not found.
    """
    obj = get_object(project, name)
    if obj is None:
        raise KeyError(f"Object not found: {name!r}")
    obj["scale"] = scale
    return project


def set_object_color(
    project: dict[str, Any],
    name: str,
    color: list[float],
) -> dict[str, Any]:
    """Set an object's base color (RGBA in [0, 1]).

    Raises:
        KeyError: If object not found.
    """
    obj = get_object(project, name)
    if obj is None:
        raise KeyError(f"Object not found: {name!r}")
    obj["color"] = color
    return project


def point_camera_at(
    project: dict[str, Any],
    target: list[float],
    distance: float = 10.0,
    elevation: float = 0.6,
) -> dict[str, Any]:
    """Position the camera to look at a target point.

    Args:
        project: Project dict.
        target: [x, y, z] target position.
        distance: Distance from target.
        elevation: Elevation angle in radians.
    """
    import math
    tx, ty, tz = target
    cam_x = tx
    cam_y = ty - distance * math.cos(elevation)
    cam_z = tz + distance * math.sin(elevation)

    rot_x = elevation
    return set_camera(
        project,
        location=[cam_x, cam_y, cam_z],
        rotation_euler=[rot_x, 0.0, 0.0],
    )
