"""Blender backend integration.

Finds the Blender executable and runs Python scripts headlessly via:
    blender --background [blend_file] --python script.py [-- extra_args]
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def find_blender() -> str:
    """Find the Blender executable.

    Search order:
      1. BLENDER_PATH environment variable
      2. shutil.which("blender")
      3. Common OS-specific installation paths

    Returns:
        Absolute path to the blender executable.

    Raises:
        RuntimeError: If Blender is not found. Message includes install instructions.
    """
    # 1. Env override
    env_path = os.environ.get("BLENDER_PATH", "").strip()
    if env_path and Path(env_path).is_file():
        return env_path

    # 2. PATH
    found = shutil.which("blender")
    if found:
        return found

    # 3. Common OS paths
    candidates = []
    if sys.platform == "win32":
        import glob
        patterns = [
            r"C:\Program Files\Blender Foundation\Blender*\blender.exe",
            r"C:\Program Files (x86)\Blender Foundation\Blender*\blender.exe",
        ]
        for pat in patterns:
            candidates.extend(glob.glob(pat))
    elif sys.platform == "darwin":
        candidates = [
            "/Applications/Blender.app/Contents/MacOS/blender",
        ]
    else:
        candidates = [
            "/usr/bin/blender",
            "/usr/local/bin/blender",
            str(Path.home() / ".local/bin/blender"),
        ]

    for path in candidates:
        if Path(path).is_file():
            return path

    raise RuntimeError(
        "Blender not found.\n"
        "Install from https://www.blender.org/download/ and ensure it is in PATH,\n"
        "or set the BLENDER_PATH environment variable to the blender executable.\n"
        "Example: export BLENDER_PATH=/usr/bin/blender"
    )


def run_script(
    script_content: str,
    blend_file: str | None = None,
    extra_args: list[str] | None = None,
    timeout: int = 300,
) -> subprocess.CompletedProcess:
    """Run a Python script in Blender headlessly.

    Args:
        script_content: Python source code to execute inside Blender.
        blend_file: Optional path to a .blend file to open first.
        extra_args: Optional list of extra args to pass after `--`.
        timeout: Maximum execution time in seconds (default 300).

    Returns:
        CompletedProcess with stdout/stderr captured.

    Raises:
        RuntimeError: If Blender is not found or script fails.
    """
    blender = find_blender()

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(script_content)
        script_path = f.name

    try:
        cmd = [blender, "--background"]
        if blend_file:
            cmd.append(blend_file)
        cmd += ["--python", script_path]
        if extra_args:
            cmd += ["--"] + extra_args

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return result
    finally:
        os.unlink(script_path)


def run_script_file(
    script_path: str,
    blend_file: str | None = None,
    extra_args: list[str] | None = None,
    timeout: int = 300,
) -> subprocess.CompletedProcess:
    """Run an existing Python script file in Blender headlessly."""
    blender = find_blender()

    cmd = [blender, "--background"]
    if blend_file:
        cmd.append(blend_file)
    cmd += ["--python", script_path]
    if extra_args:
        cmd += ["--"] + extra_args

    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def get_blender_version() -> str:
    """Return the Blender version string."""
    blender = find_blender()
    result = subprocess.run(
        [blender, "--version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    for line in result.stdout.splitlines():
        if line.strip().startswith("Blender"):
            return line.strip()
    return result.stdout.strip().splitlines()[0] if result.stdout.strip() else "unknown"
