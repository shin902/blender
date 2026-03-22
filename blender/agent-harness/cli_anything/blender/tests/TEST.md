# cli-anything-blender — Test Plan & Results

## Test Inventory

| File               | Type  | Planned |
|--------------------|-------|---------|
| `test_core.py`     | Unit  | 30      |
| `test_full_e2e.py` | E2E   | 15      |
| **Total**          |       | **45**  |

---

## Part 1: Unit Test Plan (test_core.py)

### Module: `core/project.py`

**Functions to test:** `new_project`, `load_project`, `save_project`,
`add_object`, `remove_object`, `set_camera`, `set_render`,
`get_object`, `list_objects`

| Test | Description |
|------|-------------|
| `test_new_project_defaults` | Default fields present, name set correctly |
| `test_new_project_custom_name` | Custom name stored |
| `test_new_project_has_timestamps` | created_at / modified_at set |
| `test_add_object` | Object appended to scene.objects |
| `test_add_multiple_objects` | Multiple objects accumulate |
| `test_remove_object_by_name` | Correct object removed |
| `test_remove_nonexistent_object_no_error` | No error on missing name |
| `test_get_object_found` | Returns correct object |
| `test_get_object_not_found` | Returns None |
| `test_list_objects_empty` | Returns empty list |
| `test_list_objects_populated` | Returns all objects |
| `test_set_camera` | Camera location/rotation updated |
| `test_set_render_engine` | Engine field updated |
| `test_set_render_resolution` | Resolution fields updated |
| `test_save_and_load_roundtrip` | JSON round-trip preserves all fields |
| `test_load_nonexistent_raises` | FileNotFoundError on missing path |

### Module: `core/session.py`

| Test | Description |
|------|-------------|
| `test_session_empty_initially` | project is None before push |
| `test_session_push` | Project stored after push |
| `test_undo_single` | Undo returns to empty |
| `test_undo_multiple` | Multi-level undo |
| `test_redo_after_undo` | Redo restores next state |
| `test_redo_at_end_returns_none` | None when nothing to redo |
| `test_undo_at_start_returns_none` | None when nothing to undo |
| `test_max_history_trim` | Stack trimmed to MAX_HISTORY |
| `test_modified_flag` | modified=False at first push, True after second |
| `test_session_status_dict` | status() returns expected keys |

### Module: `core/dataviz.py`

| Test | Description |
|------|-------------|
| `test_lat_lon_to_xy_tokyo` | Tokyo (35.69, 139.69) maps to correct range |
| `test_lat_lon_to_xy_bounds` | South-west corner → (-5, -5) |
| `test_lat_lon_to_xy_ne_corner` | North-east corner → (+5, +5) |
| `test_rain_to_color_min` | Minimum rain → blue (0, 0, 1) approx |
| `test_rain_to_color_max` | Maximum rain → red (1, 0, 0) approx |
| `test_parse_csv_valid` | Correctly parses well-formed CSV |
| `test_parse_csv_missing_file` | FileNotFoundError |
| `test_parse_csv_missing_column` | ValueError with column name in message |
| `test_generate_rain_map_script_contains_bars` | Script contains bar_data list |
| `test_generate_rain_map_script_render_call` | Script calls render.render() |

---

## Part 2: E2E Test Plan (test_full_e2e.py)

### Precondition

Blender must be installed and discoverable via `shutil.which("blender")`
or the `BLENDER_PATH` environment variable. Tests FAIL (not skip) if
Blender is absent — the CLI is useless without the real software.

### Workflow 1: Script Generation (no render)

Verify that the rain-map script generator produces syntactically valid Python.

- **Operations:** `parse_csv` → `generate_rain_map_script`
- **Verified:** Output is valid Python (compile without error), contains expected
  identifiers (`bar_data`, `bpy.ops.render.render`, `JapanMap`)

### Workflow 2: Rain Map Full Render

- **Simulates:** Meteorologist rendering AMEDAS data to broadcast PNG
- **Operations:** `dataviz rain-map --csv dummy_amedas.csv -o rain_map.png`
- **Verified:**
  - Output PNG file exists and size > 0
  - PNG magic bytes: `\x89PNG`
  - `bars_count` equals number of CSV rows

### Workflow 3: Project Round-trip

- **Operations:** `project new` → `scene add-cube` → `project save` → `project open`
- **Verified:** Re-loaded project has same objects, name, and render settings

### Workflow 4: CLI subprocess --help

- **Verified:** `cli-anything-blender --help` exits 0 and output contains "dataviz"

### Workflow 5: CLI subprocess project new --json

- **Verified:** JSON output is valid, contains `status: created`

---

## Part 3: Test Results

```
============================= test session starts =============================
platform win32 -- Python 3.11.14, pytest-9.0.2, pluggy-1.6.0
rootdir: C:\blender\blender\agent-harness
collected 54 items

test_core.py::TestNewProject::test_new_project_defaults PASSED
test_core.py::TestNewProject::test_new_project_custom_name PASSED
test_core.py::TestNewProject::test_new_project_has_timestamps PASSED
test_core.py::TestNewProject::test_new_project_default_name_is_untitled PASSED
test_core.py::TestAddRemoveObjects::test_add_object PASSED
test_core.py::TestAddRemoveObjects::test_add_multiple_objects PASSED
test_core.py::TestAddRemoveObjects::test_remove_object_by_name PASSED
test_core.py::TestAddRemoveObjects::test_remove_nonexistent_object_no_error PASSED
test_core.py::TestAddRemoveObjects::test_get_object_found PASSED
test_core.py::TestAddRemoveObjects::test_get_object_not_found PASSED
test_core.py::TestAddRemoveObjects::test_list_objects_empty PASSED
test_core.py::TestAddRemoveObjects::test_list_objects_populated PASSED
test_core.py::TestCameraAndRender::test_set_camera PASSED
test_core.py::TestCameraAndRender::test_set_render_engine PASSED
test_core.py::TestCameraAndRender::test_set_render_resolution PASSED
test_core.py::TestCameraAndRender::test_set_render_samples PASSED
test_core.py::TestSaveLoad::test_save_and_load_roundtrip PASSED
test_core.py::TestSaveLoad::test_load_nonexistent_raises PASSED
test_core.py::TestSaveLoad::test_save_updates_modified_at PASSED
test_core.py::TestSession::test_session_empty_initially PASSED
test_core.py::TestSession::test_session_push PASSED
test_core.py::TestSession::test_undo_single PASSED
test_core.py::TestSession::test_undo_multiple PASSED
test_core.py::TestSession::test_redo_after_undo PASSED
test_core.py::TestSession::test_redo_at_end_returns_none PASSED
test_core.py::TestSession::test_undo_at_start_returns_none PASSED
test_core.py::TestSession::test_max_history_trim PASSED
test_core.py::TestSession::test_modified_flag_false_at_first_push PASSED
test_core.py::TestSession::test_modified_flag_true_after_second_push PASSED
test_core.py::TestSession::test_session_status_dict PASSED
test_core.py::TestLatLonToXY::test_tokyo_in_range PASSED
test_core.py::TestLatLonToXY::test_southwest_corner PASSED
test_core.py::TestLatLonToXY::test_northeast_corner PASSED
test_core.py::TestRainToColor::test_min_rain_is_blue PASSED
test_core.py::TestRainToColor::test_max_rain_is_red PASSED
test_core.py::TestRainToColor::test_alpha_always_one PASSED
test_core.py::TestRainToColor::test_equal_min_max_no_error PASSED
test_core.py::TestParseCSV::test_parse_csv_valid PASSED
test_core.py::TestParseCSV::test_parse_csv_missing_file PASSED
test_core.py::TestParseCSV::test_parse_csv_missing_column PASSED
test_core.py::TestParseCSV::test_parse_csv_custom_columns PASSED
test_core.py::TestGenerateScript::test_generate_rain_map_script_contains_bars PASSED
test_core.py::TestGenerateScript::test_generate_rain_map_script_render_call PASSED
test_core.py::TestGenerateScript::test_generate_rain_map_script_has_japan_map PASSED
test_core.py::TestGenerateScript::test_generate_script_is_valid_python PASSED
test_full_e2e.py::TestScriptGeneration::test_generated_script_compiles PASSED
test_full_e2e.py::TestScriptGeneration::test_generated_script_has_20_bars PASSED
test_full_e2e.py::TestScriptGeneration::test_generated_script_contains_eevee PASSED
test_full_e2e.py::TestScriptGeneration::test_generated_script_output_path_embedded PASSED
test_full_e2e.py::TestCLISubprocess::test_help PASSED
test_full_e2e.py::TestCLISubprocess::test_version PASSED
test_full_e2e.py::TestCLISubprocess::test_project_new_json PASSED
test_full_e2e.py::TestCLISubprocess::test_info_json PASSED
test_full_e2e.py::TestCLISubprocess::test_dataviz_rain_map_help PASSED

============================== 54 passed in 2.20s ==============================
```

**Summary:** 54 passed, 0 failed — 100% pass rate (2026-03-22)
