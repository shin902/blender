"""cli-anything-blender — Command-line interface for Blender 3D automation.

Entry point: cli-anything-blender
REPL mode: invoked when no subcommand is given.

Command groups:
  project   Create/open/save/close projects
  scene     Add/remove/transform objects
  render    Render to image
  dataviz   Data visualization (CSV → 3D bar charts)
  session   Undo/redo, status
  info      Blender installation info
"""

import json
import os
import sys
from pathlib import Path

import click

from cli_anything.blender.__init__ import __version__
from cli_anything.blender.core import project as proj_mod
from cli_anything.blender.core import session as sess_mod
from cli_anything.blender.core import export as export_mod
from cli_anything.blender.core import scene as scene_mod
from cli_anything.blender.core import dataviz as dataviz_mod
from cli_anything.blender.utils import blender_backend


# ── Global session (shared across commands in REPL) ───────────────────
_SESSION = sess_mod.Session()


def _output(data: dict, as_json: bool) -> None:
    """Print data as JSON or human-readable."""
    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        for key, value in data.items():
            click.echo(f"  {key}: {value}")


def _require_project(session: sess_mod.Session) -> dict:
    """Get current project or abort."""
    if session.project is None:
        raise click.ClickException("No project open. Use: project new OR project open <path>")
    return session.project


# ── Root CLI ──────────────────────────────────────────────────────────

@click.group(invoke_without_command=True, context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--json", "as_json", is_flag=True, help="Output in JSON format")
@click.version_option(__version__, "-V", "--version")
@click.pass_context
def cli(ctx: click.Context, as_json: bool):
    """cli-anything-blender: Automate Blender 3D from the command line.

    Run without subcommand to enter interactive REPL mode.
    """
    ctx.ensure_object(dict)
    ctx.obj["as_json"] = as_json

    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)


# ── REPL ──────────────────────────────────────────────────────────────

@cli.command()
@click.pass_context
def repl(ctx: click.Context):
    """Start the interactive REPL session."""
    from cli_anything.blender.utils.repl_skin import ReplSkin

    skin = ReplSkin("blender", version=__version__)
    skin.print_banner()

    pt_session = skin.create_prompt_session()

    project_name = ""
    modified = False

    while True:
        try:
            line = skin.get_input(pt_session, project_name=project_name, modified=modified)
        except (EOFError, KeyboardInterrupt):
            skin.print_goodbye()
            break

        if not line:
            continue

        if line.lower() in ("quit", "exit", "q"):
            skin.print_goodbye()
            break

        if line.lower() in ("help", "h", "?"):
            _show_repl_help(skin)
            continue

        # Parse and dispatch the command
        try:
            args = line.split()
            ctx.invoke(cli, args=args)
        except SystemExit:
            pass
        except Exception as e:
            skin.error(str(e))

        # Update prompt state
        if _SESSION.project:
            project_name = _SESSION.project.get("name", "")
            modified = _SESSION.modified


def _show_repl_help(skin) -> None:
    """Print REPL command help."""
    from cli_anything.blender.utils.repl_skin import ReplSkin
    cmds = {
        "project new <name>":         "Create a new project",
        "project open <path>":         "Open an existing project",
        "project save [path]":         "Save current project",
        "project status":              "Show project info",
        "scene add-cube <name>":       "Add a cube to the scene",
        "scene add-sphere <name>":     "Add a sphere to the scene",
        "scene add-plane <name>":      "Add a plane to the scene",
        "scene list":                  "List all objects",
        "scene remove <name>":         "Remove an object",
        "render image -o <path>":      "Render to PNG image",
        "dataviz rain-map --csv <f>":  "Render rain data from CSV",
        "session undo":                "Undo last change",
        "session redo":                "Redo last undone change",
        "session status":              "Show session state",
        "info":                        "Show Blender installation info",
        "quit":                        "Exit the REPL",
    }
    skin.help(cmds)


# ── project group ─────────────────────────────────────────────────────

@cli.group()
@click.pass_context
def project(ctx: click.Context):
    """Project management commands."""


@project.command("new")
@click.argument("name", default="untitled")
@click.option("-o", "--output", default=None, help="Save path for the project JSON")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def project_new(ctx: click.Context, name: str, output: str | None, as_json: bool):
    """Create a new blank project."""
    as_json = as_json or ctx.obj.get("as_json", False)
    p = proj_mod.new_project(name)
    _SESSION.push(p)
    if output:
        proj_mod.save_project(p, output)
        _SESSION.path = output

    data = {"status": "created", "name": name, "path": output or ""}
    _output(data, as_json)


@project.command("open")
@click.argument("path")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def project_open(ctx: click.Context, path: str, as_json: bool):
    """Open an existing project JSON file."""
    as_json = as_json or ctx.obj.get("as_json", False)
    p = proj_mod.load_project(path)
    _SESSION.push(p)
    _SESSION.path = path

    data = {
        "status": "opened",
        "name": p.get("name", ""),
        "path": path,
        "objects": len(proj_mod.list_objects(p)),
    }
    _output(data, as_json)


@project.command("save")
@click.argument("path", required=False)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def project_save(ctx: click.Context, path: str | None, as_json: bool):
    """Save the current project to a JSON file."""
    as_json = as_json or ctx.obj.get("as_json", False)
    p = _require_project(_SESSION)
    save_path = path or _SESSION.path
    if not save_path:
        raise click.ClickException("No save path specified. Use: project save <path>")

    proj_mod.save_project(p, save_path)
    _SESSION.path = save_path

    data = {"status": "saved", "path": save_path}
    _output(data, as_json)


@project.command("status")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def project_status(ctx: click.Context, as_json: bool):
    """Show current project status."""
    as_json = as_json or ctx.obj.get("as_json", False)
    p = _require_project(_SESSION)

    data = {
        "name": p.get("name", ""),
        "path": _SESSION.path or "(unsaved)",
        "objects": len(proj_mod.list_objects(p)),
        "engine": p.get("render", {}).get("engine", ""),
        "resolution": f"{p['render']['resolution_x']}x{p['render']['resolution_y']}",
        "modified": _SESSION.modified,
    }
    _output(data, as_json)


# ── scene group ───────────────────────────────────────────────────────

@cli.group()
@click.pass_context
def scene(ctx: click.Context):
    """Scene object management commands."""


@scene.command("add-cube")
@click.argument("name")
@click.option("--loc", default="0,0,0", help="Location x,y,z")
@click.option("--scale", default="1,1,1", help="Scale x,y,z")
@click.option("--color", default="0.8,0.8,0.8", help="RGB color 0–1")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def scene_add_cube(ctx: click.Context, name: str, loc: str, scale: str, color: str, as_json: bool):
    """Add a cube to the scene."""
    as_json = as_json or ctx.obj.get("as_json", False)
    p = _require_project(_SESSION)
    location = [float(v) for v in loc.split(",")]
    scale_v = [float(v) for v in scale.split(",")]
    color_v = [float(v) for v in color.split(",")] + [1.0]

    scene_mod.add_cube(p, name, location=location, scale=scale_v, color=color_v)
    _SESSION.push(p)

    data = {"status": "added", "type": "CUBE", "name": name, "location": location}
    _output(data, as_json)


@scene.command("add-sphere")
@click.argument("name")
@click.option("--loc", default="0,0,0")
@click.option("--scale", default="1,1,1")
@click.option("--color", default="0.8,0.2,0.2")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def scene_add_sphere(ctx: click.Context, name: str, loc: str, scale: str, color: str, as_json: bool):
    """Add a sphere to the scene."""
    as_json = as_json or ctx.obj.get("as_json", False)
    p = _require_project(_SESSION)
    location = [float(v) for v in loc.split(",")]
    scale_v = [float(v) for v in scale.split(",")]
    color_v = [float(v) for v in color.split(",")] + [1.0]

    scene_mod.add_sphere(p, name, location=location, scale=scale_v, color=color_v)
    _SESSION.push(p)

    data = {"status": "added", "type": "SPHERE", "name": name, "location": location}
    _output(data, as_json)


@scene.command("add-plane")
@click.argument("name")
@click.option("--loc", default="0,0,0")
@click.option("--scale", default="1,1,1")
@click.option("--color", default="0.3,0.5,0.3")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def scene_add_plane(ctx: click.Context, name: str, loc: str, scale: str, color: str, as_json: bool):
    """Add a plane to the scene."""
    as_json = as_json or ctx.obj.get("as_json", False)
    p = _require_project(_SESSION)
    location = [float(v) for v in loc.split(",")]
    scale_v = [float(v) for v in scale.split(",")]
    color_v = [float(v) for v in color.split(",")] + [1.0]

    scene_mod.add_plane(p, name, location=location, scale=scale_v, color=color_v)
    _SESSION.push(p)

    data = {"status": "added", "type": "PLANE", "name": name, "location": location}
    _output(data, as_json)


@scene.command("remove")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def scene_remove(ctx: click.Context, name: str, as_json: bool):
    """Remove an object from the scene by name."""
    as_json = as_json or ctx.obj.get("as_json", False)
    p = _require_project(_SESSION)
    proj_mod.remove_object(p, name)
    _SESSION.push(p)

    data = {"status": "removed", "name": name}
    _output(data, as_json)


@scene.command("list")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def scene_list(ctx: click.Context, as_json: bool):
    """List all objects in the scene."""
    as_json = as_json or ctx.obj.get("as_json", False)
    p = _require_project(_SESSION)
    objects = proj_mod.list_objects(p)

    if as_json:
        click.echo(json.dumps({"objects": objects, "count": len(objects)}, indent=2))
    else:
        if not objects:
            click.echo("  (no objects in scene)")
        else:
            click.echo(f"  {'Name':<20} {'Type':<10} {'Location'}")
            click.echo(f"  {'─'*20} {'─'*10} {'─'*20}")
            for obj in objects:
                loc = obj.get("location", [0, 0, 0])
                click.echo(f"  {obj.get('name',''):<20} {obj.get('type',''):<10} {loc}")


@scene.command("move")
@click.argument("name")
@click.argument("location")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def scene_move(ctx: click.Context, name: str, location: str, as_json: bool):
    """Move an object. LOCATION format: x,y,z"""
    as_json = as_json or ctx.obj.get("as_json", False)
    p = _require_project(_SESSION)
    loc = [float(v) for v in location.split(",")]
    scene_mod.move_object(p, name, loc)
    _SESSION.push(p)

    data = {"status": "moved", "name": name, "location": loc}
    _output(data, as_json)


@scene.command("camera")
@click.option("--loc", default="0,-10,5", help="Camera location x,y,z")
@click.option("--rot", default="1.1,0,0", help="Rotation euler x,y,z (radians)")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def scene_camera(ctx: click.Context, loc: str, rot: str, as_json: bool):
    """Set camera position and rotation."""
    as_json = as_json or ctx.obj.get("as_json", False)
    p = _require_project(_SESSION)
    location = [float(v) for v in loc.split(",")]
    rotation = [float(v) for v in rot.split(",")]
    proj_mod.set_camera(p, location, rotation)
    _SESSION.push(p)

    data = {"status": "camera_set", "location": location, "rotation": rotation}
    _output(data, as_json)


# ── render group ──────────────────────────────────────────────────────

@cli.group()
@click.pass_context
def render(ctx: click.Context):
    """Rendering commands."""


@render.command("image")
@click.option("-o", "--output", required=True, help="Output PNG path")
@click.option("--engine", default=None, help="EEVEE or CYCLES")
@click.option("--samples", default=None, type=int)
@click.option("--res", default=None, help="Resolution WxH, e.g. 1920x1080")
@click.option("--timeout", default=300, type=int, help="Max render time (seconds)")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def render_image(
    ctx: click.Context,
    output: str,
    engine: str | None,
    samples: int | None,
    res: str | None,
    timeout: int,
    as_json: bool,
):
    """Render the current scene to a PNG image."""
    as_json = as_json or ctx.obj.get("as_json", False)
    p = _require_project(_SESSION)

    if engine:
        proj_mod.set_render(p, engine=engine)
    if samples:
        proj_mod.set_render(p, samples=samples)
    if res:
        w, h = res.split("x")
        proj_mod.set_render(p, resolution_x=int(w), resolution_y=int(h))

    click.echo(f"  Rendering to {output} ...")
    out = export_mod.render_project(p, output_path=output, timeout=timeout)

    data = {"status": "rendered", "output": out}
    _output(data, as_json)


# ── dataviz group ─────────────────────────────────────────────────────

@cli.group()
@click.pass_context
def dataviz(ctx: click.Context):
    """Data visualization commands."""


@dataviz.command("rain-map")
@click.option("--csv", "csv_path", required=True, help="Path to CSV file (lat,lon,rain columns)")
@click.option("-o", "--output", required=True, help="Output PNG path")
@click.option("--lat-col", default="lat", help="CSV column for latitude (default: lat)")
@click.option("--lon-col", default="lon", help="CSV column for longitude (default: lon)")
@click.option("--rain-col", default="rain", help="CSV column for rain amount (default: rain)")
@click.option("--bar-width", default=0.08, type=float, help="Bar width in Blender units")
@click.option("--height-scale", default=0.003, type=float, help="rain × scale = bar height")
@click.option("--map-texture", default=None, help="Path to Japan map image texture")
@click.option("--engine", default="EEVEE", type=click.Choice(["EEVEE", "CYCLES"]))
@click.option("--res", default="1920x1080", help="Resolution WxH")
@click.option("--samples", default=64, type=int)
@click.option("--timeout", default=300, type=int, help="Max render time (seconds)")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def dataviz_rain_map(
    ctx: click.Context,
    csv_path: str,
    output: str,
    lat_col: str,
    lon_col: str,
    rain_col: str,
    bar_width: float,
    height_scale: float,
    map_texture: str | None,
    engine: str,
    res: str,
    samples: int,
    timeout: int,
    as_json: bool,
):
    """Render AMEDAS rain gauge data as a 3D bar chart on Japan map.

    CSV must have columns: lat, lon, rain (or specify with --lat-col etc.)

    Example:
        cli-anything-blender dataviz rain-map --csv rain.csv -o rain_map.png
    """
    as_json = as_json or ctx.obj.get("as_json", False)

    res_x, res_y = (int(v) for v in res.split("x"))

    click.echo(f"  Loading CSV: {csv_path}")
    click.echo(f"  Rendering {res_x}x{res_y} with {engine} ({samples} samples)...")

    result = dataviz_mod.render_rain_map(
        csv_path=csv_path,
        output_path=output,
        lat_col=lat_col,
        lon_col=lon_col,
        rain_col=rain_col,
        bar_width=bar_width,
        height_scale=height_scale,
        map_texture_path=map_texture,
        engine=engine,
        resolution_x=res_x,
        resolution_y=res_y,
        samples=samples,
        timeout=timeout,
    )

    data = {
        "status": "rendered",
        "output": result["output_path"],
        "bars": result["bars_count"],
        "rain_min": f"{result['rain_min']:.1f} mm",
        "rain_max": f"{result['rain_max']:.1f} mm",
    }
    _output(data, as_json)


# ── session group ─────────────────────────────────────────────────────

@cli.group()
@click.pass_context
def session(ctx: click.Context):
    """Session management (undo/redo, status)."""


@session.command("undo")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def session_undo(ctx: click.Context, as_json: bool):
    """Undo the last change."""
    as_json = as_json or ctx.obj.get("as_json", False)
    p = _SESSION.undo()
    if p is None:
        raise click.ClickException("Nothing to undo")
    data = {"status": "undone", "project": p.get("name", "")}
    _output(data, as_json)


@session.command("redo")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def session_redo(ctx: click.Context, as_json: bool):
    """Redo the last undone change."""
    as_json = as_json or ctx.obj.get("as_json", False)
    p = _SESSION.redo()
    if p is None:
        raise click.ClickException("Nothing to redo")
    data = {"status": "redone", "project": p.get("name", "")}
    _output(data, as_json)


@session.command("status")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def session_status(ctx: click.Context, as_json: bool):
    """Show session state."""
    as_json = as_json or ctx.obj.get("as_json", False)
    data = _SESSION.status()
    _output(data, as_json)


# ── info command ──────────────────────────────────────────────────────

@cli.command("info")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def info(ctx: click.Context, as_json: bool):
    """Show Blender installation info."""
    as_json = as_json or ctx.obj.get("as_json", False)
    try:
        blender_path = blender_backend.find_blender()
        version = blender_backend.get_blender_version()
        data = {
            "blender_path": blender_path,
            "version": version,
            "status": "found",
        }
    except RuntimeError as e:
        data = {"status": "not_found", "error": str(e)}

    _output(data, as_json)


if __name__ == "__main__":
    cli()
