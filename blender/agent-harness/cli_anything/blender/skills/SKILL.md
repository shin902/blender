---
name: "cli-anything-blender"
description: "Automate Blender 3D from the command line: create scenes, add objects, render images, and visualize CSV data as 3D bar charts on a Japan map."
---

# cli-anything-blender

CLI harness for Blender 3D automation. Generates bpy Python scripts and runs them
via `blender --background --python script.py`.

## Prerequisites

- Python 3.10+
- Blender installed and in PATH (or set `BLENDER_PATH=/path/to/blender`)
- `pip install cli-anything-blender` (or `pip install -e .` from source)

## Installation

```bash
pip install cli-anything-blender
cli-anything-blender --help
```

## Basic Usage

```bash
# Interactive REPL
cli-anything-blender

# One-shot commands
cli-anything-blender project new my_scene -o scene.cliblend.json
cli-anything-blender scene add-cube Box1 --loc 0,0,1 --color 0.2,0.6,1.0
cli-anything-blender render image -o output.png

# Rain data visualization
cli-anything-blender dataviz rain-map --csv amedas.csv -o japan_rain.png
```

## Command Groups

| Group     | Description                                         |
|-----------|-----------------------------------------------------|
| `project` | Create, open, save, and inspect projects            |
| `scene`   | Add/remove/move objects (cube, sphere, plane)       |
| `render`  | Render the scene to a PNG image via Blender         |
| `dataviz` | Visualize CSV data as 3D bar charts                 |
| `session` | Undo/redo, session status                           |
| `info`    | Show Blender path and version                       |

## Key Commands

### project
```bash
project new [NAME] [-o PATH]     # Create new project JSON
project open PATH                # Open existing project JSON
project save [PATH]              # Save current project
project status                   # Show project info
```

### scene
```bash
scene add-cube NAME [--loc x,y,z] [--scale x,y,z] [--color r,g,b]
scene add-sphere NAME [--loc x,y,z]
scene add-plane NAME [--loc x,y,z]
scene remove NAME
scene list
scene camera --loc x,y,z --rot x,y,z
scene move NAME x,y,z
```

### render
```bash
render image -o OUTPUT.png [--engine EEVEE|CYCLES] [--samples N] [--res 1920x1080]
```

### dataviz
```bash
dataviz rain-map \
  --csv amedas.csv \        # CSV with lat,lon,rain columns
  -o japan_rain.png \       # Output PNG
  --engine EEVEE \          # EEVEE (fast) or CYCLES (quality)
  --res 1920x1080 \
  --samples 64 \
  --height-scale 0.003 \    # rain_mm × scale = bar height
  --bar-width 0.08          # bar width in Blender units
```

**CSV format:**
```csv
lat,lon,rain
35.689,139.691,100.0
34.693,135.502,899.1
```

### session
```bash
session undo
session redo
session status
```

## JSON Output Mode

All commands support `--json` for machine-readable output:

```bash
cli-anything-blender --json project new test
# → {"status": "created", "name": "test", "path": ""}

cli-anything-blender --json dataviz rain-map --csv data.csv -o out.png
# → {"status": "rendered", "output": "out.png", "bars": 800, "rain_min": "...", "rain_max": "..."}
```

## Agent Usage Notes

1. Check Blender is available: `cli-anything-blender --json info`
2. For rain maps, CSV must have `lat`, `lon`, `rain` columns (or specify with `--lat-col` etc.)
3. Render times: EEVEE ~10s for 800 bars at 1080p; CYCLES ~2min
4. Output PNG path must be an absolute path on Windows
5. Use `--timeout` to increase limit for large scenes (default: 300s)

## Environment Variables

| Variable       | Description                                 |
|----------------|---------------------------------------------|
| `BLENDER_PATH` | Override Blender executable path            |
| `NO_COLOR`     | Disable ANSI colors in REPL output          |
