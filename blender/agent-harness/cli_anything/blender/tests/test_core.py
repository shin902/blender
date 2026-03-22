"""Unit tests for cli-anything-blender core modules.

All tests use synthetic data — no external dependencies (Blender not required).
"""

import json
import os
import tempfile
from copy import deepcopy

import pytest

from cli_anything.blender.core import project as proj_mod
from cli_anything.blender.core import session as sess_mod
from cli_anything.blender.core import dataviz as dv_mod
from cli_anything.blender.core import scene as scene_mod


# ── core/project.py ───────────────────────────────────────────────────

class TestNewProject:
    def test_new_project_defaults(self):
        p = proj_mod.new_project()
        assert "scene" in p
        assert "render" in p
        assert "objects" in p["scene"]
        assert "camera" in p["scene"]

    def test_new_project_custom_name(self):
        p = proj_mod.new_project("my_test")
        assert p["name"] == "my_test"

    def test_new_project_has_timestamps(self):
        p = proj_mod.new_project()
        assert p["created_at"] != ""
        assert p["modified_at"] != ""

    def test_new_project_default_name_is_untitled(self):
        p = proj_mod.new_project()
        assert p["name"] == "untitled"


class TestAddRemoveObjects:
    def test_add_object(self):
        p = proj_mod.new_project()
        proj_mod.add_object(p, {"type": "CUBE", "name": "Box1", "location": [0, 0, 0]})
        assert len(p["scene"]["objects"]) == 1
        assert p["scene"]["objects"][0]["name"] == "Box1"

    def test_add_multiple_objects(self):
        p = proj_mod.new_project()
        for i in range(5):
            proj_mod.add_object(p, {"type": "CUBE", "name": f"Cube_{i}"})
        assert len(p["scene"]["objects"]) == 5

    def test_remove_object_by_name(self):
        p = proj_mod.new_project()
        proj_mod.add_object(p, {"type": "CUBE", "name": "A"})
        proj_mod.add_object(p, {"type": "CUBE", "name": "B"})
        proj_mod.remove_object(p, "A")
        names = [o["name"] for o in p["scene"]["objects"]]
        assert "A" not in names
        assert "B" in names

    def test_remove_nonexistent_object_no_error(self):
        p = proj_mod.new_project()
        proj_mod.remove_object(p, "DoesNotExist")  # should not raise

    def test_get_object_found(self):
        p = proj_mod.new_project()
        proj_mod.add_object(p, {"type": "SPHERE", "name": "Ball"})
        obj = proj_mod.get_object(p, "Ball")
        assert obj is not None
        assert obj["type"] == "SPHERE"

    def test_get_object_not_found(self):
        p = proj_mod.new_project()
        assert proj_mod.get_object(p, "Missing") is None

    def test_list_objects_empty(self):
        p = proj_mod.new_project()
        assert proj_mod.list_objects(p) == []

    def test_list_objects_populated(self):
        p = proj_mod.new_project()
        proj_mod.add_object(p, {"name": "X"})
        proj_mod.add_object(p, {"name": "Y"})
        assert len(proj_mod.list_objects(p)) == 2


class TestCameraAndRender:
    def test_set_camera(self):
        p = proj_mod.new_project()
        proj_mod.set_camera(p, [1.0, 2.0, 3.0], [0.5, 0.0, 0.0])
        assert p["scene"]["camera"]["location"] == [1.0, 2.0, 3.0]
        assert p["scene"]["camera"]["rotation_euler"] == [0.5, 0.0, 0.0]

    def test_set_render_engine(self):
        p = proj_mod.new_project()
        proj_mod.set_render(p, engine="CYCLES")
        assert p["render"]["engine"] == "CYCLES"

    def test_set_render_resolution(self):
        p = proj_mod.new_project()
        proj_mod.set_render(p, resolution_x=3840, resolution_y=2160)
        assert p["render"]["resolution_x"] == 3840
        assert p["render"]["resolution_y"] == 2160

    def test_set_render_samples(self):
        p = proj_mod.new_project()
        proj_mod.set_render(p, samples=256)
        assert p["render"]["samples"] == 256


class TestSaveLoad:
    def test_save_and_load_roundtrip(self, tmp_path):
        p = proj_mod.new_project("roundtrip_test")
        proj_mod.add_object(p, {"type": "CUBE", "name": "TestCube", "location": [1, 2, 3]})
        proj_mod.set_render(p, engine="CYCLES", samples=128)

        path = str(tmp_path / "test.cliblend.json")
        proj_mod.save_project(p, path)
        loaded = proj_mod.load_project(path)

        assert loaded["name"] == "roundtrip_test"
        assert loaded["render"]["engine"] == "CYCLES"
        assert loaded["render"]["samples"] == 128
        assert len(loaded["scene"]["objects"]) == 1
        assert loaded["scene"]["objects"][0]["name"] == "TestCube"

    def test_load_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            proj_mod.load_project("/nonexistent/path/project.json")

    def test_save_updates_modified_at(self, tmp_path):
        p = proj_mod.new_project()
        original_ts = p["modified_at"]
        import time; time.sleep(0.01)
        path = str(tmp_path / "ts_test.json")
        proj_mod.save_project(p, path)
        loaded = proj_mod.load_project(path)
        assert loaded["modified_at"] >= original_ts


# ── core/session.py ───────────────────────────────────────────────────

class TestSession:
    def test_session_empty_initially(self):
        s = sess_mod.Session()
        assert s.project is None

    def test_session_push(self):
        s = sess_mod.Session()
        p = proj_mod.new_project("test")
        s.push(p)
        assert s.project is not None
        assert s.project["name"] == "test"

    def test_undo_single(self):
        s = sess_mod.Session()
        p1 = proj_mod.new_project("p1")
        p2 = proj_mod.new_project("p2")
        s.push(p1)
        s.push(p2)
        result = s.undo()
        assert result["name"] == "p1"

    def test_undo_multiple(self):
        s = sess_mod.Session()
        for i in range(5):
            s.push(proj_mod.new_project(f"p{i}"))
        s.undo()
        s.undo()
        assert s.project["name"] == "p2"

    def test_redo_after_undo(self):
        s = sess_mod.Session()
        s.push(proj_mod.new_project("a"))
        s.push(proj_mod.new_project("b"))
        s.undo()
        r = s.redo()
        assert r["name"] == "b"

    def test_redo_at_end_returns_none(self):
        s = sess_mod.Session()
        s.push(proj_mod.new_project())
        assert s.redo() is None

    def test_undo_at_start_returns_none(self):
        s = sess_mod.Session()
        s.push(proj_mod.new_project())
        assert s.undo() is None

    def test_max_history_trim(self):
        s = sess_mod.Session()
        for i in range(sess_mod.MAX_HISTORY + 10):
            s.push(proj_mod.new_project(f"p{i}"))
        assert s.history_depth() == sess_mod.MAX_HISTORY

    def test_modified_flag_false_at_first_push(self):
        s = sess_mod.Session()
        s.push(proj_mod.new_project())
        assert s.modified is False

    def test_modified_flag_true_after_second_push(self):
        s = sess_mod.Session()
        s.push(proj_mod.new_project())
        s.push(proj_mod.new_project())
        assert s.modified is True

    def test_session_status_dict(self):
        s = sess_mod.Session()
        status = s.status()
        assert "has_project" in status
        assert "can_undo" in status
        assert "can_redo" in status
        assert "history_depth" in status


# ── core/dataviz.py ───────────────────────────────────────────────────

class TestLatLonToXY:
    def test_tokyo_in_range(self):
        x, y = dv_mod.lat_lon_to_xy(35.689, 139.691)
        assert -5.0 <= x <= 5.0
        assert -5.0 <= y <= 5.0

    def test_southwest_corner(self):
        x, y = dv_mod.lat_lon_to_xy(dv_mod.JAPAN_MIN_LAT, dv_mod.JAPAN_MIN_LON)
        assert abs(x - (-5.0)) < 0.001
        assert abs(y - (-5.0)) < 0.001

    def test_northeast_corner(self):
        x, y = dv_mod.lat_lon_to_xy(dv_mod.JAPAN_MAX_LAT, dv_mod.JAPAN_MAX_LON)
        assert abs(x - 5.0) < 0.001
        assert abs(y - 5.0) < 0.001


class TestRainToColor:
    def test_min_rain_is_blue(self):
        r, g, b, a = dv_mod.rain_to_color(0.0, 0.0, 100.0)
        assert b > 0.5
        assert r < 0.5

    def test_max_rain_is_red(self):
        r, g, b, a = dv_mod.rain_to_color(100.0, 0.0, 100.0)
        assert r > 0.5
        assert b < 0.5

    def test_alpha_always_one(self):
        _, _, _, a = dv_mod.rain_to_color(50.0, 0.0, 100.0)
        assert a == 1.0

    def test_equal_min_max_no_error(self):
        result = dv_mod.rain_to_color(50.0, 50.0, 50.0)
        assert len(result) == 4


class TestParseCSV:
    def test_parse_csv_valid(self, tmp_path):
        csv_file = tmp_path / "rain.csv"
        csv_file.write_text("lat,lon,rain\n35.0,135.0,100.0\n36.0,136.0,200.0\n")
        rows = dv_mod.parse_csv(str(csv_file))
        assert len(rows) == 2
        assert rows[0]["lat"] == 35.0
        assert rows[1]["rain"] == 200.0

    def test_parse_csv_missing_file(self):
        with pytest.raises(FileNotFoundError):
            dv_mod.parse_csv("/no/such/file.csv")

    def test_parse_csv_missing_column(self, tmp_path):
        csv_file = tmp_path / "bad.csv"
        csv_file.write_text("name,value\nfoo,1\n")
        with pytest.raises(ValueError, match="missing required columns"):
            dv_mod.parse_csv(str(csv_file))

    def test_parse_csv_custom_columns(self, tmp_path):
        csv_file = tmp_path / "custom.csv"
        csv_file.write_text("latitude,longitude,precipitation\n35.0,135.0,50.5\n")
        rows = dv_mod.parse_csv(
            str(csv_file),
            lat_col="latitude",
            lon_col="longitude",
            rain_col="precipitation",
        )
        assert rows[0]["rain"] == 50.5


class TestGenerateScript:
    def test_generate_rain_map_script_contains_bars(self, tmp_path):
        rows = [
            {"lat": 35.0, "lon": 135.0, "rain": 100.0},
            {"lat": 36.0, "lon": 136.0, "rain": 200.0},
        ]
        script = dv_mod.generate_rain_map_script(
            rows, output_path=str(tmp_path / "out.png")
        )
        assert "bar_data" in script
        assert len(script) > 100

    def test_generate_rain_map_script_render_call(self, tmp_path):
        rows = [{"lat": 35.0, "lon": 135.0, "rain": 50.0}]
        script = dv_mod.generate_rain_map_script(
            rows, output_path=str(tmp_path / "out.png")
        )
        assert "bpy.ops.render.render" in script

    def test_generate_rain_map_script_has_japan_map(self, tmp_path):
        rows = [{"lat": 35.0, "lon": 135.0, "rain": 50.0}]
        script = dv_mod.generate_rain_map_script(
            rows, output_path=str(tmp_path / "out.png")
        )
        assert "JapanMap" in script

    def test_generate_script_is_valid_python(self, tmp_path):
        rows = [{"lat": 35.0, "lon": 135.0, "rain": 100.0}]
        script = dv_mod.generate_rain_map_script(
            rows, output_path=str(tmp_path / "out.png")
        )
        # Should compile without SyntaxError
        compile(script, "<generated>", "exec")
