"""E2E tests for cli-anything-blender.

Tests require Blender to be installed. Tests FAIL (not skip) if Blender absent.
Uses _resolve_cli() to test against the installed command or python -m fallback.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from cli_anything.blender.core import dataviz as dv_mod
from cli_anything.blender.utils import blender_backend


# ── CLI resolver ──────────────────────────────────────────────────────

def _resolve_cli(name: str) -> list[str]:
    """Resolve installed CLI command; falls back to python -m for dev.

    Set env CLI_ANYTHING_FORCE_INSTALLED=1 to require the installed command.
    """
    import shutil
    force = os.environ.get("CLI_ANYTHING_FORCE_INSTALLED", "").strip() == "1"
    path = shutil.which(name)
    if path:
        print(f"[_resolve_cli] Using installed command: {path}")
        return [path]
    if force:
        raise RuntimeError(f"{name} not found in PATH. Install with: pip install -e .")
    module = "cli_anything.blender.blender_cli"
    print(f"[_resolve_cli] Falling back to: {sys.executable} -m {module}")
    return [sys.executable, "-m", module]


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def tmp_dir(tmp_path):
    return str(tmp_path)


@pytest.fixture
def dummy_csv(tmp_path) -> str:
    """Create a small AMEDAS-style CSV with 20 stations."""
    import csv
    path = tmp_path / "amedas_dummy.csv"
    stations = [
        ("Sapporo",    43.06,  141.35,  856.0),
        ("Aomori",     40.82,  140.74, 1306.0),
        ("Morioka",    39.70,  141.17, 1235.0),
        ("Sendai",     38.26,  140.88, 1249.0),
        ("Akita",      39.72,  140.09, 1770.0),
        ("Yamagata",   38.24,  140.36, 1202.0),
        ("Fukushima",  37.76,  140.47, 1113.0),
        ("Tokyo",      35.69,  139.69,  100.0),  # low rain for color contrast
        ("Yokohama",   35.46,  139.64, 1735.0),
        ("Nagoya",     35.17,  136.97, 1529.0),
        ("Osaka",      34.69,  135.52,  899.0),
        ("Kobe",       34.69,  135.19, 1281.0),
        ("Kyoto",      35.01,  135.73, 1488.0),
        ("Hiroshima",  34.40,  132.46, 1540.0),
        ("Takamatsu",  34.34,  134.04, 1082.0),
        ("Matsuyama",  33.84,  132.77, 1315.0),
        ("Kochi",      33.56,  133.54, 2661.0),  # high rain for color contrast
        ("Fukuoka",    33.58,  130.38, 1611.0),
        ("Nagasaki",   32.74,  129.87, 1923.0),
        ("Kagoshima",  31.55,  130.55, 2277.0),
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["station_name", "lat", "lon", "rain"])
        for row in stations:
            writer.writerow(row)
    return str(path)


# ── Script generation E2E (no Blender needed) ────────────────────────

class TestScriptGeneration:
    """Verify generated bpy scripts are structurally correct."""

    def test_generated_script_compiles(self, dummy_csv, tmp_dir):
        rows = dv_mod.parse_csv(dummy_csv)
        script = dv_mod.generate_rain_map_script(
            rows, output_path=os.path.join(tmp_dir, "out.png")
        )
        # Must compile without SyntaxError
        compile(script, "<rain_map_script>", "exec")

    def test_generated_script_has_20_bars(self, dummy_csv, tmp_dir):
        rows = dv_mod.parse_csv(dummy_csv)
        script = dv_mod.generate_rain_map_script(
            rows, output_path=os.path.join(tmp_dir, "out.png")
        )
        # Each bar is one tuple in bar_data list
        bar_lines = [l for l in script.splitlines() if l.strip().endswith("),")]
        assert len(bar_lines) == 20

    def test_generated_script_contains_eevee(self, dummy_csv, tmp_dir):
        rows = dv_mod.parse_csv(dummy_csv)
        script = dv_mod.generate_rain_map_script(
            rows, output_path=os.path.join(tmp_dir, "out.png"), engine="EEVEE"
        )
        assert "EEVEE" in script

    def test_generated_script_output_path_embedded(self, dummy_csv, tmp_dir):
        out = os.path.join(tmp_dir, "my_render.png")
        rows = dv_mod.parse_csv(dummy_csv)
        script = dv_mod.generate_rain_map_script(rows, output_path=out)
        assert "my_render.png" in script


# ── Blender backend E2E ───────────────────────────────────────────────

class TestBlenderBackend:
    """Tests that invoke real Blender. Fail if Blender not installed."""

    def _get_blender(self):
        try:
            return blender_backend.find_blender()
        except RuntimeError as e:
            pytest.fail(f"Blender not found (required for E2E tests): {e}")

    def test_blender_found(self):
        blender = self._get_blender()
        assert blender and Path(blender).exists()
        print(f"\n  Blender: {blender}")

    def test_blender_version_string(self):
        self._get_blender()
        ver = blender_backend.get_blender_version()
        assert "Blender" in ver
        print(f"\n  Version: {ver}")

    def test_run_trivial_script(self, tmp_dir):
        self._get_blender()
        sentinel = os.path.join(tmp_dir, "sentinel.txt")
        script = f"""
import bpy
with open({sentinel!r}, 'w') as f:
    f.write('ok')
"""
        result = blender_backend.run_script(script, timeout=30)
        assert result.returncode == 0
        assert Path(sentinel).exists()
        assert Path(sentinel).read_text() == "ok"


class TestRainMapRender:
    """Full rain-map render pipeline using real Blender."""

    def _get_blender(self):
        try:
            return blender_backend.find_blender()
        except RuntimeError as e:
            pytest.fail(f"Blender not found (required for render tests): {e}")

    def test_render_rain_map_produces_png(self, dummy_csv, tmp_dir):
        self._get_blender()
        output = os.path.join(tmp_dir, "rain_map.png")

        result = dv_mod.render_rain_map(
            csv_path=dummy_csv,
            output_path=output,
            resolution_x=320,
            resolution_y=240,
            samples=4,
            engine="EEVEE",
            timeout=120,
        )

        assert Path(output).exists(), f"Output PNG not found: {output}"
        size = Path(output).stat().st_size
        assert size > 0, "Output PNG is empty"
        print(f"\n  PNG: {output} ({size:,} bytes)")
        print(f"  Bars: {result['bars_count']}")
        print(f"  Rain range: {result['rain_min']:.1f} – {result['rain_max']:.1f} mm")

    def test_render_output_is_valid_png(self, dummy_csv, tmp_dir):
        self._get_blender()
        output = os.path.join(tmp_dir, "rain_valid.png")
        dv_mod.render_rain_map(
            csv_path=dummy_csv,
            output_path=output,
            resolution_x=160,
            resolution_y=120,
            samples=4,
            timeout=120,
        )
        # Verify PNG magic bytes
        with open(output, "rb") as f:
            header = f.read(8)
        assert header[:4] == b'\x89PNG', f"Not a valid PNG file: {header!r}"

    def test_render_bar_count_matches_csv(self, dummy_csv, tmp_dir):
        self._get_blender()
        output = os.path.join(tmp_dir, "count_test.png")
        result = dv_mod.render_rain_map(
            csv_path=dummy_csv,
            output_path=output,
            resolution_x=160,
            resolution_y=120,
            samples=4,
            timeout=120,
        )
        assert result["bars_count"] == 20


# ── CLI subprocess tests ──────────────────────────────────────────────

class TestCLISubprocess:
    CLI_BASE = _resolve_cli("cli-anything-blender")

    def _run(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            self.CLI_BASE + args,
            capture_output=True,
            text=True,
            check=check,
        )

    def test_help(self):
        result = self._run(["--help"])
        assert result.returncode == 0
        assert "dataviz" in result.stdout

    def test_version(self):
        result = self._run(["--version"])
        assert result.returncode == 0

    def test_project_new_json(self, tmp_dir):
        out = os.path.join(tmp_dir, "test.cliblend.json")
        result = self._run(["--json", "project", "new", "myproject", "-o", out])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["status"] == "created"
        assert data["name"] == "myproject"
        assert Path(out).exists()

    def test_info_json(self):
        result = self._run(["--json", "info"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "status" in data

    def test_dataviz_rain_map_help(self):
        result = self._run(["dataviz", "rain-map", "--help"])
        assert result.returncode == 0
        assert "--csv" in result.stdout
