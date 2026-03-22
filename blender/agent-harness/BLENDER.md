# Blender CLI Harness — SOP

## Backend Engine

**Blender** uses `bpy` (Blender Python API) as its backend. All automation is done by:
- Generating Python scripts that use `bpy`
- Running them via: `blender --background [file.blend] --python script.py`

The CLI does NOT reimplement bpy. It generates valid Python scripts and hands them
to the real Blender for execution and rendering.

## Data Model

Blender projects are `.blend` files (binary). For CLI state management, we use:
- **JSON project files** (`*.cliblend.json`) to describe scene setup declaratively
- **Generated bpy scripts** (`*.py`) that the Blender backend executes
- **Rendered outputs** (PNG, EXR, MP4) produced by Blender itself

### JSON Project Schema

```json
{
  "name": "my_project",
  "version": "1.0",
  "scene": {
    "objects": [...],
    "camera": { "location": [x, y, z], "rotation": [x, y, z] },
    "lights": [...],
    "world": { "background_color": [r, g, b, a] }
  },
  "render": {
    "engine": "CYCLES",
    "resolution_x": 1920,
    "resolution_y": 1080,
    "samples": 128,
    "output_path": "/tmp/render"
  }
}
```

## Command Groups

| Group      | Purpose                                    |
|------------|--------------------------------------------|
| `project`  | Create, open, save, close projects         |
| `scene`    | Add/remove/transform objects               |
| `material` | Apply colors and materials to objects      |
| `camera`   | Set camera position and target             |
| `render`   | Render to image or animation               |
| `script`   | Run raw bpy Python scripts                 |
| `dataviz`  | Data visualization (CSV → 3D bar charts)   |
| `session`  | Undo/redo, history                         |

## Backend Integration

`blender` executable is required. Install from https://www.blender.org/download/

### Finding Blender

Search order:
1. `BLENDER_PATH` environment variable
2. `shutil.which("blender")`
3. Common OS paths:
   - Windows: `C:\Program Files\Blender Foundation\Blender*\blender.exe`
   - macOS: `/Applications/Blender.app/Contents/MacOS/blender`
   - Linux: `/usr/bin/blender`, `/usr/local/bin/blender`, `~/.local/share/Steam/...`

### Running Scripts

```python
blender --background --python script.py
blender --background existing.blend --python script.py
blender --background --python script.py -- --arg1 value1  # pass args after --
```

### Script Template

All generated scripts follow this structure:

```python
import bpy
import sys
import json

# Parse CLI args passed after `-- `
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

# Clear default scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# ... scene setup ...

# Render
bpy.ops.render.render(write_still=True)
```

## Data Visualization: Rain Map

The primary use case from the original project: visualize AMEDAS rain gauge data
on a 3D map of Japan.

### Input: `rain_data.csv`
```
lat,lon,rain
35.689,139.691,1045.9
34.693,135.502,899.1
```

### Output: 800+ colored 3D bars on a Japan map

### Coordinate Mapping

Japan bounding box:
- Latitude:  20.0 (south) — 46.0 (north)
- Longitude: 122.0 (west) — 154.0 (east)

Mapped to Blender XY plane (-5 to +5 range for a 10x10 unit map):
```python
x = (lon - 122.0) / (154.0 - 122.0) * 10.0 - 5.0
y = (lat  -  20.0) / ( 46.0 -  20.0) * 10.0 - 5.0
z = rain * height_scale
```

Color gradient: blue (low rain) → cyan → green → yellow → red (high rain)
using HSV: hue = 0.66 (blue) → 0.0 (red), mapped by rain/rain_max

## Rendering Pipeline

1. `dataviz rain-map --csv data.csv --output render.png` triggers:
   1. Parse CSV → list of (lat, lon, rain) tuples
   2. Generate `_rain_viz.py` bpy script
   3. Run `blender --background --python _rain_viz.py`
   4. Return path to rendered PNG

## Key Files

| File                          | Purpose                                  |
|-------------------------------|------------------------------------------|
| `core/project.py`             | JSON project CRUD                        |
| `core/session.py`             | Undo/redo (deep-copy, 50 levels)         |
| `core/export.py`              | Script generation + blender invocation   |
| `core/scene.py`               | Object/light/camera management           |
| `core/dataviz.py`             | CSV → 3D bar chart logic                 |
| `utils/blender_backend.py`    | Find + invoke blender executable         |
| `utils/repl_skin.py`          | Unified REPL skin (copied from plugin)   |
| `blender_cli.py`              | Main Click CLI entry point               |
