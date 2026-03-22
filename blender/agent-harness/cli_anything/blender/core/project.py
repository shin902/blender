"""Project management for cli-anything-blender.

Projects are stored as JSON files (.cliblend.json) describing the scene
declaratively. Blender is invoked to render from these descriptions.
"""

import json
import os
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_PROJECT: dict[str, Any] = {
    "version": "1.0",
    "created_at": "",
    "modified_at": "",
    "name": "untitled",
    "scene": {
        "objects": [],
        "camera": {
            "location": [0.0, -10.0, 5.0],
            "rotation_euler": [1.1, 0.0, 0.0],
        },
        "lights": [
            {
                "type": "SUN",
                "location": [5.0, 5.0, 10.0],
                "energy": 3.0,
            }
        ],
        "world": {
            "background_color": [0.05, 0.05, 0.05, 1.0],
        },
    },
    "render": {
        "engine": "EEVEE",
        "resolution_x": 1920,
        "resolution_y": 1080,
        "samples": 64,
        "output_path": "",
        "file_format": "PNG",
    },
}


def new_project(name: str = "untitled") -> dict[str, Any]:
    """Create a new blank project."""
    proj = deepcopy(DEFAULT_PROJECT)
    proj["name"] = name
    now = datetime.utcnow().isoformat()
    proj["created_at"] = now
    proj["modified_at"] = now
    return proj


def load_project(path: str) -> dict[str, Any]:
    """Load a project from a JSON file.

    Args:
        path: Path to the .cliblend.json file.

    Returns:
        Project dict.

    Raises:
        FileNotFoundError: If file does not exist.
        ValueError: If file is not valid JSON.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Project not found: {path}")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_project(project: dict[str, Any], path: str) -> None:
    """Save a project to a JSON file.

    Args:
        project: Project dict.
        path: Destination path (will be created if needed).
    """
    project["modified_at"] = datetime.utcnow().isoformat()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(project, f, indent=2, ensure_ascii=False)


def add_object(project: dict[str, Any], obj: dict[str, Any]) -> dict[str, Any]:
    """Add an object to the scene.

    Args:
        project: Project dict (mutated in place).
        obj: Object descriptor dict. Must contain 'type' and 'name'.
            Example: {'type': 'CUBE', 'name': 'MyCube',
                      'location': [0,0,0], 'scale': [1,1,1]}

    Returns:
        The mutated project dict.
    """
    project["scene"]["objects"].append(obj)
    return project


def remove_object(project: dict[str, Any], name: str) -> dict[str, Any]:
    """Remove an object by name.

    Args:
        project: Project dict (mutated in place).
        name: Object name.

    Returns:
        The mutated project dict.
    """
    project["scene"]["objects"] = [
        o for o in project["scene"]["objects"] if o.get("name") != name
    ]
    return project


def set_camera(
    project: dict[str, Any],
    location: list[float],
    rotation_euler: list[float],
) -> dict[str, Any]:
    """Set camera position and rotation.

    Args:
        project: Project dict (mutated).
        location: [x, y, z] in Blender units.
        rotation_euler: [x, y, z] in radians.
    """
    project["scene"]["camera"]["location"] = location
    project["scene"]["camera"]["rotation_euler"] = rotation_euler
    return project


def set_render(
    project: dict[str, Any],
    engine: str | None = None,
    resolution_x: int | None = None,
    resolution_y: int | None = None,
    samples: int | None = None,
    output_path: str | None = None,
    file_format: str | None = None,
) -> dict[str, Any]:
    """Update render settings."""
    r = project["render"]
    if engine is not None:
        r["engine"] = engine
    if resolution_x is not None:
        r["resolution_x"] = resolution_x
    if resolution_y is not None:
        r["resolution_y"] = resolution_y
    if samples is not None:
        r["samples"] = samples
    if output_path is not None:
        r["output_path"] = output_path
    if file_format is not None:
        r["file_format"] = file_format
    return project


def get_object(project: dict[str, Any], name: str) -> dict[str, Any] | None:
    """Get an object by name. Returns None if not found."""
    for obj in project["scene"]["objects"]:
        if obj.get("name") == name:
            return obj
    return None


def list_objects(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Return list of all scene objects."""
    return project["scene"]["objects"]
