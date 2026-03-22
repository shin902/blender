"""Data visualization for cli-anything-blender.

Provides the rain-map command: reads a CSV with lat/lon/rain columns and
generates a Blender bpy script that places 3D bars (cubes) on a Japan map,
colored by rain intensity.
"""

import csv
import json
import math
import os
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

from cli_anything.blender.utils.blender_backend import run_script

# 国土数値情報 N03（行政区域）派生 GeoJSON — N03/MLIT データを元にした公開データ
_GSI_GEOJSON_URL = (
    "https://raw.githubusercontent.com/dataofjapan/land/master/japan.geojson"
)
_GEOJSON_CACHE = Path.home() / ".cache" / "cli-anything-blender" / "japan.geojson"

# タイルソース定義
_TILE_SOURCES = {
    "std": "https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png",
    "pale": "https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png",
    "relief": "https://cyberjapandata.gsi.go.jp/xyz/relief/{z}/{x}/{y}.png",
    "photo": "https://cyberjapandata.gsi.go.jp/xyz/seamlessphoto/{z}/{x}/{y}.jpg",
}
_TILE_CACHE = Path.home() / ".cache" / "cli-anything-blender" / "tiles"


# Japan bounding box
JAPAN_MIN_LAT = 20.0
JAPAN_MAX_LAT = 46.0
JAPAN_MIN_LON = 122.0
JAPAN_MAX_LON = 154.0

# Blender plane size (units)
PLANE_SIZE = 10.0


def _merc_y(lat_deg: float) -> float:
    """緯度 → Web Mercator Y 値 (ln(tan(lat) + sec(lat)))。"""
    lat_r = math.radians(lat_deg)
    return math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r))


# Japan bbox の Mercator Y extents（lat_lon_to_xy の Y 変換に使用）
_JAPAN_MERC_Y_MIN = _merc_y(JAPAN_MIN_LAT)  # ≈ 0.3567（lat 20°N）
_JAPAN_MERC_Y_MAX = _merc_y(JAPAN_MAX_LAT)  # ≈ 0.9063（lat 46°N）

# Simplified Japan island outlines (lat, lon) — approximate Natural Earth 1:110m
_JAPAN_ISLANDS_LATLON = {
    "Hokkaido": [
        (45.49, 141.93), (45.04, 142.93), (44.33, 145.50),
        (43.44, 145.72), (42.36, 143.00), (41.45, 140.42),
        (42.20, 139.86), (42.61, 140.04), (43.05, 140.61),
        (44.00, 141.17),
    ],
    "Honshu": [
        (41.46, 141.47), (40.52, 141.47), (39.68, 141.17),
        (38.44, 141.44), (37.25, 141.07), (36.42, 140.89),
        (35.73, 140.87), (35.49, 139.63), (34.97, 138.89),
        (34.71, 137.50), (34.58, 136.72), (33.81, 135.65),
        (34.07, 135.10), (34.23, 133.98), (33.95, 132.99),
        (34.42, 131.82), (33.96, 131.18), (33.54, 130.40),
        (34.20, 130.97), (34.72, 131.82), (35.10, 132.65),
        (35.51, 133.27), (35.38, 134.22), (36.22, 135.83),
        (36.72, 137.32), (37.51, 138.88), (38.47, 139.75),
        (39.73, 140.05), (40.84, 140.74),
    ],
    "Shikoku": [
        (33.47, 132.52), (33.86, 134.43), (33.93, 134.76),
        (34.07, 135.22), (33.61, 135.10), (33.26, 134.65),
        (33.02, 133.65), (32.91, 132.78), (33.18, 132.53),
    ],
    "Kyushu": [
        (33.91, 130.86), (33.97, 131.86), (33.24, 131.63),
        (32.48, 131.34), (31.55, 130.57), (31.21, 130.19),
        (31.44, 129.63), (32.18, 129.70), (32.66, 129.82),
        (33.21, 129.69), (33.72, 130.17),
    ],
    "Okinawa": [
        (27.05, 128.12), (26.83, 128.28), (26.65, 128.16),
        (26.20, 127.65), (26.11, 127.45), (26.45, 126.36),
        (26.71, 126.20), (26.83, 126.74),
    ],
}


def lat_lon_to_xy(lat: float, lon: float) -> tuple[float, float]:
    """Map lat/lon within Japan's bounding box to Blender XY coordinates.

    The plane spans from -PLANE_SIZE/2 to +PLANE_SIZE/2 in both axes.

    Args:
        lat: Latitude in degrees.
        lon: Longitude in degrees.

    Returns:
        (x, y) Blender coordinates.
    """
    half = PLANE_SIZE / 2.0
    x = (lon - JAPAN_MIN_LON) / (JAPAN_MAX_LON - JAPAN_MIN_LON) * PLANE_SIZE - half
    # Mercator Y: 航空写真タイル（Web Mercator）と座標系を一致させる
    y = (_merc_y(lat) - _JAPAN_MERC_Y_MIN) / (_JAPAN_MERC_Y_MAX - _JAPAN_MERC_Y_MIN) * PLANE_SIZE - half
    return (x, y)


def _deg2tile(lat_deg: float, lon_deg: float, zoom: int) -> tuple[int, int]:
    """lat/lon → XYZ スリッピーマップタイル番号 (整数)。"""
    lat_r = math.radians(lat_deg)
    n = 2 ** zoom
    x = int((lon_deg + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def _latlon_to_tile_frac(lat_deg: float, lon_deg: float, zoom: int) -> tuple[float, float]:
    """lat/lon → タイル座標の小数値 (サブタイルピクセル計算用)。"""
    lat_r = math.radians(lat_deg)
    n = 2 ** zoom
    frac_x = (lon_deg + 180.0) / 360.0 * n
    frac_y = (1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n
    return frac_x, frac_y



def _fetch_tile(url: str, headers: dict) -> "Image.Image | None":
    """タイルを URL からダウンロードして PIL Image を返す。失敗時は None。"""
    import io
    from PIL import Image
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return Image.open(io.BytesIO(resp.read())).convert("RGB")
    except Exception:
        return None


def fetch_map_texture(
    zoom: int = 6,
    tile_source: str = "std",
    cache_path: "Path | None" = None,
    force_refresh: bool = False,
) -> Path:
    """国土地理院タイルをダウンロード・スティッチして Japan bbox にクロップした JPEG を返す。

    初回のみダウンロード、2回目以降はキャッシュを返す。

    Args:
        zoom: ズームレベル（デフォルト 6）。
        tile_source: タイルソース ("std", "pale", "photo")。
        cache_path: キャッシュ保存先パス。省略時はデフォルトキャッシュディレクトリ。
        force_refresh: True の場合キャッシュを無視して再ダウンロード。

    Returns:
        stitched JPEG の Path。
    """
    from PIL import Image

    if tile_source not in _TILE_SOURCES:
        raise ValueError(f"Unknown tile_source: {tile_source!r}. Choose from {list(_TILE_SOURCES)}")

    url_template = _TILE_SOURCES[tile_source]
    cache_file = Path(cache_path or _TILE_CACHE / f"japan_{tile_source}_z{zoom}.jpg")
    if cache_file.exists() and not force_refresh:
        print(f"タイルキャッシュ使用: {cache_file}")
        return cache_file

    cache_file.parent.mkdir(parents=True, exist_ok=True)

    # タイル範囲計算（北西=x_min/y_min, 南東=x_max/y_max）
    x_min, y_min = _deg2tile(JAPAN_MAX_LAT, JAPAN_MIN_LON, zoom)
    x_max, y_max = _deg2tile(JAPAN_MIN_LAT, JAPAN_MAX_LON, zoom)
    tile_w = x_max - x_min + 1
    tile_h = y_max - y_min + 1
    px = 256
    print(f"タイル範囲: x={x_min}-{x_max} ({tile_w}枚), y={y_min}-{y_max} ({tile_h}枚), 合計 {tile_w * tile_h} タイル")

    headers = {"User-Agent": "cli-anything-blender/1.0"}

    canvas = Image.new("RGB", (tile_w * px, tile_h * px), (6, 46, 106))

    for ix, tx in enumerate(range(x_min, x_max + 1)):
        for iy, ty in enumerate(range(y_min, y_max + 1)):
            tile = _fetch_tile(url_template.format(z=zoom, x=tx, y=ty), headers)
            if tile is not None:
                canvas.paste(tile, (ix * px, iy * px))

    # Mercator ピクセル座標で bbox にクロップ
    frac_x_left, frac_y_top = _latlon_to_tile_frac(JAPAN_MAX_LAT, JAPAN_MIN_LON, zoom)
    frac_x_right, frac_y_bottom = _latlon_to_tile_frac(JAPAN_MIN_LAT, JAPAN_MAX_LON, zoom)
    crop_x0 = max(0, int((frac_x_left - x_min) * px))
    crop_y0 = max(0, int((frac_y_top - y_min) * px))
    crop_x1 = min(canvas.width, int((frac_x_right - x_min) * px))
    crop_y1 = min(canvas.height, int((frac_y_bottom - y_min) * px))
    canvas = canvas.crop((crop_x0, crop_y0, crop_x1, crop_y1))
    canvas.save(cache_file, "JPEG", quality=90)
    print(f"地図テクスチャ保存: {cache_file} ({canvas.width}x{canvas.height}px)")
    return cache_file


def _rdp(points: list[tuple[float, float]], epsilon: float) -> list[tuple[float, float]]:
    """Ramer-Douglas-Peucker polygon simplification (iterative).

    Args:
        points: List of (x, y) coordinate pairs.
        epsilon: Maximum allowed deviation in same units as coordinates.

    Returns:
        Simplified list of (x, y) pairs.
    """
    if len(points) < 3:
        return list(points)

    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]

    while stack:
        start, end = stack.pop()
        if end - start < 2:
            continue
        x1, y1 = points[start]
        x2, y2 = points[end]
        dx, dy = x2 - x1, y2 - y1
        len_sq = dx * dx + dy * dy

        max_dist, max_idx = 0.0, start
        for i in range(start + 1, end):
            x, y = points[i]
            if len_sq == 0:
                dist = math.hypot(x - x1, y - y1)
            else:
                t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / len_sq))
                dist = math.hypot(x - x1 - t * dx, y - y1 - t * dy)
            if dist > max_dist:
                max_dist, max_idx = dist, i

        if max_dist > epsilon:
            keep[max_idx] = True
            stack.append((start, max_idx))
            stack.append((max_idx, end))

    return [points[i] for i in range(len(points)) if keep[i]]


def fetch_japan_geojson(
    url: str = _GSI_GEOJSON_URL,
    cache_path: Path | None = None,
) -> dict:
    """Download and cache Japan prefecture GeoJSON (国土数値情報 N03 派生).

    データは初回のみダウンロードし、以降はキャッシュを使用します。

    Args:
        url: GeoJSON ダウンロード URL。
        cache_path: ローカルキャッシュファイルパス。

    Returns:
        パース済み GeoJSON dict。
    """
    if cache_path is None:
        cache_path = _GEOJSON_CACHE
    cache_path = Path(cache_path)

    if cache_path.exists():
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"国土数値情報 N03 GeoJSON をダウンロード中: {url}")
    urllib.request.urlretrieve(url, cache_path)
    print(f"キャッシュ保存: {cache_path}")

    with open(cache_path, encoding="utf-8") as f:
        return json.load(f)


def extract_japan_polygons(
    geojson: dict,
    epsilon: float = 0.08,
    min_bbox_area: float = 0.02,
) -> list[list[tuple[float, float]]]:
    """GeoJSON から日本の陸地ポリゴンを抽出・簡略化する。

    Args:
        geojson: パース済み GeoJSON FeatureCollection。
        epsilon: RDP 簡略化の許容誤差（度単位）。
        min_bbox_area: 含めるポリゴンの最小バウンディングボックス面積（deg²）。
                       小さな離島をフィルタリングするために使用。

    Returns:
        ポリゴンリスト。各要素は (lat, lon) タプルのリスト。
    """
    polygons: list[list[tuple[float, float]]] = []
    seen: set[tuple[float, float, float, float]] = set()

    for feature in geojson.get("features", []):
        geom = feature.get("geometry") or {}
        geom_type = geom.get("type", "")

        # GeoJSON 座標は [lon, lat] の順
        rings: list[list] = []
        if geom_type == "Polygon":
            rings = [geom["coordinates"][0]]
        elif geom_type == "MultiPolygon":
            rings = [poly[0] for poly in geom["coordinates"]]

        for ring in rings:
            if len(ring) < 4:
                continue
            lons = [c[0] for c in ring]
            lats = [c[1] for c in ring]
            bbox_area = (max(lons) - min(lons)) * (max(lats) - min(lats))
            if bbox_area < min_bbox_area:
                continue

            # バウンディングボックスで重複排除（府県境界の重複を防ぐ）
            key = (round(min(lons), 2), round(min(lats), 2),
                   round(max(lons), 2), round(max(lats), 2))
            if key in seen:
                continue
            seen.add(key)

            # GeoJSON: [lon, lat] → RDP 簡略化 → (lat, lon) に変換
            pts = [(c[0], c[1]) for c in ring]
            simplified = _rdp(pts, epsilon)
            if len(simplified) < 3:
                continue
            polygons.append([(c[1], c[0]) for c in simplified])  # → (lat, lon)

    return polygons


def rain_to_color(rain: float, rain_min: float, rain_max: float) -> tuple[float, float, float, float]:
    """Map a rain value to an RGBA color (blue=low, red=high).

    Uses HSV with S=1, V=1, hue from 0.66 (blue) to 0.0 (red).

    Args:
        rain: Current rain value.
        rain_min: Minimum rain value in dataset.
        rain_max: Maximum rain value in dataset.

    Returns:
        (r, g, b, 1.0) tuple in [0, 1] range.
    """
    if rain_max == rain_min:
        return (0.0, 0.5, 1.0, 1.0)

    t = (rain - rain_min) / (rain_max - rain_min)
    hue = 0.66 * (1.0 - t)
    h = hue * 6.0
    i = int(h) % 6
    f = h - int(h)
    q = 1.0 - f

    if i == 0:
        r, g, b = 1.0, f, 0.0
    elif i == 1:
        r, g, b = q, 1.0, 0.0
    elif i == 2:
        r, g, b = 0.0, 1.0, f
    elif i == 3:
        r, g, b = 0.0, q, 1.0
    elif i == 4:
        r, g, b = f, 0.0, 1.0
    else:
        r, g, b = 1.0, 0.0, q

    return (r, g, b, 1.0)


def parse_csv(
    csv_path: str,
    lat_col: str = "lat",
    lon_col: str = "lon",
    rain_col: str = "rain",
) -> list[dict[str, float]]:
    """Parse a rain data CSV file.

    Args:
        csv_path: Path to the CSV file.
        lat_col: Column name for latitude.
        lon_col: Column name for longitude.
        rain_col: Column name for rain amount.

    Returns:
        List of dicts with keys: lat, lon, rain.

    Raises:
        FileNotFoundError: If CSV does not exist.
        ValueError: If required columns are missing.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    rows = []
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row")

        fields = [c.strip() for c in reader.fieldnames]
        missing = [c for c in [lat_col, lon_col, rain_col] if c not in fields]
        if missing:
            raise ValueError(
                f"CSV missing required columns: {missing}. "
                f"Available: {fields}"
            )

        for row in reader:
            try:
                rows.append({
                    "lat": float(row[lat_col]),
                    "lon": float(row[lon_col]),
                    "rain": float(row[rain_col]),
                })
            except (ValueError, KeyError):
                continue  # Skip malformed rows

    if not rows:
        raise ValueError("No valid data rows found in CSV")

    return rows


def generate_rain_map_script(
    rows: list[dict[str, float]],
    output_path: str,
    bar_width: float = 0.08,
    height_scale: float = 0.0015,
    map_texture_path: str | None = None,
    engine: str = "EEVEE",
    resolution_x: int = 1920,
    resolution_y: int = 1080,
    samples: int = 64,
    camera_location: tuple[float, float, float] = (-0.5, -8.0, 22.0),
    camera_rotation: tuple[float, float, float] = (0.42, 0.0, 0.0),
    background_color: tuple[float, float, float, float] = (0.04, 0.07, 0.14, 1.0),
    land_polygons: list[list[tuple[float, float]]] | None = None,
) -> str:
    """Generate a bpy Python script for the rain map visualization.

    Args:
        rows: List of dicts with lat, lon, rain keys.
        output_path: Path for the rendered PNG.
        bar_width: Width of each bar cube (Blender units).
        height_scale: Multiply rain value by this for bar height.
        map_texture_path: Optional path to Japan map image texture.
        engine: Render engine ('EEVEE', 'CYCLES').
        resolution_x: Render width in pixels.
        resolution_y: Render height in pixels.
        samples: Render samples.
        camera_location: Camera XYZ position.
        camera_rotation: Camera Euler rotation (radians).
        background_color: RGBA world background.

    Returns:
        Python source code string.
    """
    rain_values = [r["rain"] for r in rows]
    rain_min = min(rain_values)
    rain_max = max(rain_values)

    # 陸地ポリゴン: GeoJSON由来データ優先、なければハードコードデータにフォールバック
    if land_polygons is not None:
        land_polys_xy = [
            [lat_lon_to_xy(lat, lon) for lat, lon in poly]
            for poly in land_polygons
        ]
    else:
        land_polys_xy = [
            [lat_lon_to_xy(lat, lon) for lat, lon in pts]
            for pts in _JAPAN_ISLANDS_LATLON.values()
        ]

    lines = [
        "import bpy",
        "",
        "# ── Clear scene ──────────────────────────────────────────────────────",
        "bpy.ops.object.select_all(action='SELECT')",
        "bpy.ops.object.delete(use_global=False)",
        "",
        "# ── World background ─────────────────────────────────────────────────",
        "world = bpy.context.scene.world",
        "if world is None:",
        "    world = bpy.data.worlds.new('World')",
        "    bpy.context.scene.world = world",
        "world.use_nodes = True",
        "bg_node = world.node_tree.nodes.get('Background')",
        "if bg_node:",
        f"    bg_node.inputs[0].default_value = {background_color}",
        "    bg_node.inputs[1].default_value = 0.3",
        "",
        "# ── Sun light ────────────────────────────────────────────────────────",
        "sun_data = bpy.data.lights.new(name='Sun', type='SUN')",
        "sun_data.energy = 5.0",
        "sun_obj = bpy.data.objects.new('Sun', sun_data)",
        "bpy.context.scene.collection.objects.link(sun_obj)",
        "sun_obj.location = (3.0, -8.0, 15.0)",
        "sun_obj.rotation_euler = (0.4, 0.0, 0.5)",
        "",
        "# ── Ocean base plane (JapanMap) ───────────────────────────────────────",
        f"bpy.ops.mesh.primitive_plane_add(size={PLANE_SIZE * 1.2:.1f}, location=(0, 0, -0.05))",
        "map_plane = bpy.context.active_object",
        "map_plane.name = 'JapanMap'",
        "map_mat = bpy.data.materials.new(name='OceanMaterial')",
        "map_mat.use_nodes = True",
        "map_mat.node_tree.nodes.clear()",
        "emit_ocean = map_mat.node_tree.nodes.new('ShaderNodeEmission')",
        "emit_ocean.inputs['Color'].default_value = (0.04, 0.18, 0.42, 1.0)",
        "emit_ocean.inputs['Strength'].default_value = 0.8",
        "out_ocean = map_mat.node_tree.nodes.new('ShaderNodeOutputMaterial')",
        "map_mat.node_tree.links.new(emit_ocean.outputs['Emission'], out_ocean.inputs['Surface'])",
        "map_plane.data.materials.append(map_mat)",
        "",
        "# ── 陸地ポリゴン（Curve fill — 法線問題なし・凹多角形対応）────────",
        f"land_polys = {repr(land_polys_xy)}",
        "",
        "# 共有マテリアル",
        "_lm = bpy.data.materials.new('LandMat')",
        "_lm.use_nodes = True",
        "_lm.node_tree.nodes.clear()",
        "_le = _lm.node_tree.nodes.new('ShaderNodeEmission')",
        "_le.inputs['Color'].default_value = (0.28, 0.42, 0.20, 1.0)",
        "_le.inputs['Strength'].default_value = 1.0",
        "_lo = _lm.node_tree.nodes.new('ShaderNodeOutputMaterial')",
        "_lm.node_tree.links.new(_le.outputs['Emission'], _lo.inputs['Surface'])",
        "",
        "for _pi, _pts in enumerate(land_polys):",
        "    _cd = bpy.data.curves.new(f'Land_{_pi}', type='CURVE')",
        "    _cd.dimensions = '2D'",
        "    _cd.fill_mode = 'BOTH'",
        "    _cd.extrude = 0.03",
        "    _sp = _cd.splines.new('POLY')",
        "    _sp.points.add(len(_pts) - 1)",
        "    for _i, (_x, _y) in enumerate(_pts):",
        "        _sp.points[_i].co = (_x, _y, 0.0, 1.0)",
        "    _sp.use_cyclic_u = True",
        "    _co = bpy.data.objects.new(f'Land_{_pi}', _cd)",
        "    bpy.context.scene.collection.objects.link(_co)",
        "    _co.location.z = 0.02",
        "    _cd.materials.append(_lm)",
        "",
        "# ── Rain bars (emission shader — reliable color in all Blender versions) ─",
        f"bar_width = {bar_width}",
        "",
        "bar_data = [",
    ]

    for row in rows:
        x, y = lat_lon_to_xy(row["lat"], row["lon"])
        r, g, b, a = rain_to_color(row["rain"], rain_min, rain_max)
        h = max(row["rain"] * height_scale, 0.01)
        lines.append(f"    ({x:.4f}, {y:.4f}, {h:.4f}, {r:.4f}, {g:.4f}, {b:.4f}),")

    lines += [
        "]",
        "",
        "for i, (bx, by, bh, cr, cg, cb) in enumerate(bar_data):",
        "    bpy.ops.mesh.primitive_cube_add(size=1.0)",
        "    bar = bpy.context.active_object",
        "    bar.name = f'Bar_{i}'",
        "    bar.scale = (bar_width, bar_width, bh)",
        "    bar.location = (bx, by, bh / 2)",
        "    mat = bpy.data.materials.new(f'BarMat_{i}')",
        "    mat.use_nodes = True",
        "    mat.node_tree.nodes.clear()",
        "    emit = mat.node_tree.nodes.new('ShaderNodeEmission')",
        "    emit.inputs['Color'].default_value = (cr, cg, cb, 1.0)",
        "    emit.inputs['Strength'].default_value = 1.5",
        "    out_node = mat.node_tree.nodes.new('ShaderNodeOutputMaterial')",
        "    mat.node_tree.links.new(emit.outputs['Emission'], out_node.inputs['Surface'])",
        "    bar.data.materials.append(mat)",
        "",
        "# ── Camera ───────────────────────────────────────────────────────────",
        "cam_data = bpy.data.cameras.new('Camera')",
        "cam_data.lens = 30",
        "cam_obj = bpy.data.objects.new('Camera', cam_data)",
        "bpy.context.scene.collection.objects.link(cam_obj)",
        f"cam_obj.location = {camera_location}",
        f"cam_obj.rotation_euler = {camera_rotation}",
        "bpy.context.scene.camera = cam_obj",
        "",
        "# ── Render (Blender 3.x / 4.x / 5.x compatible) ─────────────────────",
        f"_req_engine = '{engine}'",
        "if _req_engine == 'CYCLES':",
        "    _engine_id = 'CYCLES'",
        "    bpy.context.scene.render.engine = 'CYCLES'",
        "else:",
        "    # EEVEE name differs by version: 3.x/5.x→BLENDER_EEVEE, 4.2+→BLENDER_EEVEE_NEXT",
        "    _engine_id = None",
        "    for _candidate in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'):",
        "        try:",
        "            bpy.context.scene.render.engine = _candidate",
        "            _engine_id = _candidate",
        "            break",
        "        except TypeError:",
        "            pass",
        "    if _engine_id is None:",
        "        bpy.context.scene.render.engine = 'CYCLES'",
        "        _engine_id = 'CYCLES'",
        f"bpy.context.scene.render.resolution_x = {resolution_x}",
        f"bpy.context.scene.render.resolution_y = {resolution_y}",
        "bpy.context.scene.render.image_settings.file_format = 'PNG'",
        f"bpy.context.scene.render.filepath = {output_path!r}",
        "if _engine_id == 'CYCLES':",
        f"    bpy.context.scene.cycles.samples = {samples}",
        "    bpy.context.scene.cycles.device = 'CPU'",
        "else:",
        "    try:",
        f"        bpy.context.scene.eevee.taa_render_samples = {samples}",
        "    except Exception: pass",
        "",
        "bpy.ops.render.render(write_still=True)",
        f"print('Rendered to: {output_path}')",
        f"print('Bars generated: {len(rows)}')",
        f"print('Rain range: {rain_min:.1f} - {rain_max:.1f} mm')",
    ]

    return "\n".join(lines)


def render_rain_map(
    csv_path: str,
    output_path: str,
    lat_col: str = "lat",
    lon_col: str = "lon",
    rain_col: str = "rain",
    bar_width: float = 0.08,
    height_scale: float = 0.0015,
    map_texture_path: str | None = None,
    engine: str = "EEVEE",
    resolution_x: int = 1920,
    resolution_y: int = 1080,
    samples: int = 64,
    timeout: int = 300,
    use_gsi_data: bool = True,
    geojson_url: str = _GSI_GEOJSON_URL,
    geojson_cache: Path | None = None,
    rdp_epsilon: float = 0.08,
    min_bbox_area: float = 0.02,
) -> dict[str, Any]:
    """Full pipeline: CSV → Blender render → PNG.

    Args:
        csv_path: Path to CSV with lat/lon/rain columns.
        output_path: Path for the output PNG file.
        lat_col: CSV column name for latitude.
        lon_col: CSV column name for longitude.
        rain_col: CSV column name for rain amount.
        bar_width: Width of each bar in Blender units.
        height_scale: Multiplier for bar height (rain × scale = Blender Z).
        map_texture_path: Optional path to Japan map image texture.
        engine: Render engine ('EEVEE' or 'CYCLES').
        resolution_x: Output width in pixels.
        resolution_y: Output height in pixels.
        samples: Render samples.
        timeout: Max render time in seconds.
        use_gsi_data: 国土数値情報 N03 GeoJSON を使用するか (False でハードコードに戻す)。
        geojson_url: GeoJSON ダウンロード URL。
        geojson_cache: GeoJSON ローカルキャッシュパス。
        rdp_epsilon: RDP 簡略化の許容誤差（度）。
        min_bbox_area: 最小ポリゴン面積フィルタ（deg²）。

    Returns:
        Dict with keys: output_path, bars_count, rain_min, rain_max.

    Raises:
        FileNotFoundError: If CSV not found.
        ValueError: If CSV is malformed.
        RuntimeError: If Blender not found or rendering fails.
    """
    rows = parse_csv(csv_path, lat_col, lon_col, rain_col)
    rain_values = [r["rain"] for r in rows]

    # 国土数値情報 GeoJSON から陸地ポリゴンを取得
    land_polygons: list[list[tuple[float, float]]] | None = None
    if use_gsi_data:
        try:
            geojson = fetch_japan_geojson(url=geojson_url, cache_path=geojson_cache)
            land_polygons = extract_japan_polygons(
                geojson, epsilon=rdp_epsilon, min_bbox_area=min_bbox_area
            )
            print(f"国土数値情報 N03: {len(land_polygons)} ポリゴン取得")
        except Exception as e:
            print(f"Warning: GeoJSON 取得失敗、ハードコードデータを使用: {e}")

    script = generate_rain_map_script(
        rows,
        output_path=output_path,
        bar_width=bar_width,
        height_scale=height_scale,
        map_texture_path=map_texture_path,
        engine=engine,
        resolution_x=resolution_x,
        resolution_y=resolution_y,
        samples=samples,
        land_polygons=land_polygons,
    )

    result = run_script(script, timeout=timeout)

    if result.returncode != 0:
        raise RuntimeError(
            f"Blender rendering failed (exit {result.returncode}):\n"
            f"STDOUT:\n{result.stdout[-3000:]}\n"
            f"STDERR:\n{result.stderr[-2000:]}"
        )

    return {
        "output_path": output_path,
        "bars_count": len(rows),
        "rain_min": min(rain_values),
        "rain_max": max(rain_values),
        "script_stdout": result.stdout,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 地形データ単独 PNG 化 (CSV 無し)
# ──────────────────────────────────────────────────────────────────────────────

def generate_japan_map_script(
    land_polygons: list[list[tuple[float, float]]],
    output_path: str,
    engine: str = "EEVEE",
    resolution_x: int = 1920,
    resolution_y: int = 1080,
    samples: int = 64,
    camera_location: tuple[float, float, float] = (0.0, 0.0, 22.0),
    camera_rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    camera_type: str = "ORTHO",
    camera_lens: float = 35.0,
    ortho_zoom: float = 1.0,
    background_color: tuple[float, float, float, float] = (0.04, 0.07, 0.14, 1.0),
    ocean_color: tuple[float, float, float] = (0.04, 0.18, 0.42),
    land_color: tuple[float, float, float] = (0.28, 0.42, 0.20),
    texture_path: "Path | None" = None,
) -> str:
    """地形データ（GeoJSON ポリゴン）だけを Blender でレンダリングする bpy スクリプトを生成する。

    Blender Curve オブジェクトを使い、fill_mode='BOTH' で各ポリゴンを
    2D 塗りつぶし形状にする。bmesh 法線問題を回避し凹多角形にも対応。

    Args:
        land_polygons: extract_japan_polygons() が返す (lat, lon) リストのリスト。
        output_path: 出力 PNG パス。
        engine: レンダーエンジン ('EEVEE' or 'CYCLES')。
        resolution_x/y: 解像度。
        samples: レンダーサンプル数。
        camera_location: カメラ位置 (default: 真上から俯瞰)。
        camera_rotation: カメラ回転 (Euler rad)。
        background_color: ワールド背景 RGB。
        ocean_color: 海の RGB（texture_path 未使用時）。
        land_color: 陸地の RGB（texture_path 未使用時）。
        texture_path: 航空写真 JPEG パス。指定した場合、ベースプレーンにテクスチャを貼付け
                      陸地ポリゴンは非表示にする。

    Returns:
        Blender bpy スクリプト文字列。
    """
    # Python 側で lat/lon → Blender XY を事前計算して埋め込む
    polys_xy = [
        [lat_lon_to_xy(lat, lon) for lat, lon in poly]
        for poly in land_polygons
    ]

    oc = ocean_color
    lc = land_color
    bg = background_color
    # Blender は forward slash を要求（Windows パス対策）
    tex_path_str = str(texture_path).replace("\\", "/") if texture_path else None

    # ── ortho_scale 計算 ──────────────────────────────────────────────────
    # landscape 時、Blender の ortho_scale = カメラ幅 (world units)
    # height = ortho_scale × (res_y / res_x)
    # bbox 高さ (PLANE_SIZE) を完全に表示するには:
    #   ortho_scale ≥ PLANE_SIZE × (res_x / res_y)
    _aspect = resolution_x / resolution_y
    _ortho = PLANE_SIZE * _aspect * 1.05 * ortho_zoom   # 5% パディング、ortho_zoom < 1 でズームイン
    # PERSP 時は低角度で地平線まで見えるため海プレーンを大きくする
    _ocean_size = _ortho * (4.0 if camera_type == "PERSP" else 1.3)

    lines = [
        "import bpy",
        "",
        "# ── シーンクリア ────────────────────────────────────────────────",
        "bpy.ops.object.select_all(action='SELECT')",
        "bpy.ops.object.delete(use_global=False)",
        "",
        "# ── ワールド背景 ─────────────────────────────────────────────────",
        "world = bpy.context.scene.world or bpy.data.worlds.new('World')",
        "bpy.context.scene.world = world",
        "world.use_nodes = True",
        "bg = world.node_tree.nodes.get('Background')",
        "if bg:",
        f"    bg.inputs[0].default_value = ({bg[0]}, {bg[1]}, {bg[2]}, 1.0)",
        "    bg.inputs[1].default_value = 0.2",
        "",
        "# ── 海ベースプレーン ─────────────────────────────────────────────",
        f"bpy.ops.mesh.primitive_plane_add(size={_ocean_size:.2f}, location=(0, 0, -0.01))",
        "ocean = bpy.context.active_object",
        "ocean.name = 'Ocean'",
        "_om = bpy.data.materials.new('OceanMat')",
        "_om.use_nodes = True",
        "_om.node_tree.nodes.clear()",
        "_oe = _om.node_tree.nodes.new('ShaderNodeEmission')",
        f"_oe.inputs['Color'].default_value = ({oc[0]}, {oc[1]}, {oc[2]}, 1.0)",
        "_oe.inputs['Strength'].default_value = 1.0",
        "_oo = _om.node_tree.nodes.new('ShaderNodeOutputMaterial')",
        "_om.node_tree.links.new(_oe.outputs['Emission'], _oo.inputs['Surface'])",
        "ocean.data.materials.append(_om)",
        "",
    ]

    if tex_path_str:
        # 航空写真テクスチャを bbox ぴったりのプレーン（size=PLANE_SIZE）に貼り付け
        # UV 座標を頂点位置から明示的に設定してトライアングル継ぎ目の灰色を防ぐ
        lines += [
            "# ── 航空写真テクスチャプレーン（bbox = -5..5, -5..5）────────────",
            f"bpy.ops.mesh.primitive_plane_add(size={PLANE_SIZE:.1f}, location=(0, 0, -0.005))",
            "_tp = bpy.context.active_object",
            "_tp.name = 'AerialTexPlane'",
            "_tm = bpy.data.materials.new('AerialTexMat')",
            "_tm.use_nodes = True",
            "_tm.node_tree.nodes.clear()",
            "# Generated 座標（オブジェクト bbox を 0-1 に自動マップ）でテクスチャを貼る",
            "_tc = _tm.node_tree.nodes.new('ShaderNodeTexCoord')",
            "_tex = _tm.node_tree.nodes.new('ShaderNodeTexImage')",
            f"_tex.image = bpy.data.images.load({tex_path_str!r})",
            "_tex.interpolation = 'Cubic'",
            "_emit = _tm.node_tree.nodes.new('ShaderNodeEmission')",
            "_emit.inputs['Strength'].default_value = 1.0",
            "_tmo = _tm.node_tree.nodes.new('ShaderNodeOutputMaterial')",
            "_tm.node_tree.links.new(_tc.outputs['Generated'], _tex.inputs['Vector'])",
            "_tm.node_tree.links.new(_tex.outputs['Color'], _emit.inputs['Color'])",
            "_tm.node_tree.links.new(_emit.outputs['Emission'], _tmo.inputs['Surface'])",
            "_tp.data.materials.append(_tm)",
            "",
        ]
    else:
        # テクスチャなし時のみ陸地ポリゴンを描画
        lines += [
            "# ── 陸地マテリアル（共通）────────────────────────────────────────",
            "_lm = bpy.data.materials.new('LandMat')",
            "_lm.use_nodes = True",
            "_lm.node_tree.nodes.clear()",
            "_le = _lm.node_tree.nodes.new('ShaderNodeEmission')",
            f"_le.inputs['Color'].default_value = ({lc[0]}, {lc[1]}, {lc[2]}, 1.0)",
            "_le.inputs['Strength'].default_value = 1.0",
            "_lo = _lm.node_tree.nodes.new('ShaderNodeOutputMaterial')",
            "_lm.node_tree.links.new(_le.outputs['Emission'], _lo.inputs['Surface'])",
            "",
            "# ── 陸地ポリゴン（Curve fill で法線問題を回避）───────────────────",
            f"_polys = {repr(polys_xy)}",
            "",
            "for _pi, _pts in enumerate(_polys):",
            "    _cd = bpy.data.curves.new(f'Land_{_pi}', type='CURVE')",
            "    _cd.dimensions = '2D'",
            "    _cd.fill_mode = 'BOTH'",
            "    _cd.extrude = 0.03",
            "    _sp = _cd.splines.new('POLY')",
            "    _sp.points.add(len(_pts) - 1)",
            "    for _i, (_x, _y) in enumerate(_pts):",
            "        _sp.points[_i].co = (_x, _y, 0.0, 1.0)",
            "    _sp.use_cyclic_u = True",
            "    _co = bpy.data.objects.new(f'Land_{_pi}', _cd)",
            "    bpy.context.scene.collection.objects.link(_co)",
            "    _co.location.z = 0.02",
            "    _cd.materials.append(_lm)",
            "",
        ]

    lines += [
        "# ── カメラ ───────────────────────────────────────────────────────",
        "cam_data = bpy.data.cameras.new('Camera')",
        f"cam_data.type = {camera_type!r}",
        *(
            [f"cam_data.ortho_scale = {_ortho:.4f}"]
            if camera_type == "ORTHO"
            else [f"cam_data.lens = {camera_lens}"]
        ),
        "cam_obj = bpy.data.objects.new('Camera', cam_data)",
        "bpy.context.scene.collection.objects.link(cam_obj)",
        f"cam_obj.location = {camera_location}",
        f"cam_obj.rotation_euler = {camera_rotation}",
        "bpy.context.scene.camera = cam_obj",
        "",
        "# ── レンダー設定 ─────────────────────────────────────────────────",
        f"_req = '{engine}'",
        "for _en in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT', 'CYCLES'):",
        "    if _req == 'CYCLES' and _en != 'CYCLES': continue",
        "    try:",
        "        bpy.context.scene.render.engine = _en",
        "        break",
        "    except TypeError:",
        "        pass",
        f"bpy.context.scene.render.resolution_x = {resolution_x}",
        f"bpy.context.scene.render.resolution_y = {resolution_y}",
        "bpy.context.scene.render.image_settings.file_format = 'PNG'",
        f"bpy.context.scene.render.filepath = {output_path!r}",
        "try:",
        f"    bpy.context.scene.eevee.taa_render_samples = {samples}",
        "except Exception: pass",
        "",
        "bpy.ops.render.render(write_still=True)",
        f"print('Map rendered to: {output_path}')",
        f"print('Land polygons: {len(land_polygons)}')",
    ]

    return "\n".join(lines)


def render_japan_map(
    output_path: str,
    engine: str = "EEVEE",
    resolution_x: int = 1920,
    resolution_y: int = 1080,
    samples: int = 64,
    timeout: int = 300,
    geojson_url: str = _GSI_GEOJSON_URL,
    geojson_cache: Path | None = None,
    rdp_epsilon: float = 0.05,
    min_bbox_area: float = 0.01,
    camera_location: tuple[float, float, float] = (-1.14, 0.66, 22.0),
    camera_rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    camera_type: str = "ORTHO",
    camera_lens: float = 35.0,
    ortho_zoom: float = 0.86,
    background_color: tuple[float, float, float, float] = (0.04, 0.07, 0.14, 1.0),
    ocean_color: tuple[float, float, float] = (0.04, 0.18, 0.42),
    land_color: tuple[float, float, float] = (0.28, 0.42, 0.20),
    tile_zoom: int = 5,
    tile_source: "str | None" = "std",
    force_tile_refresh: bool = False,
) -> dict[str, Any]:
    """地形データのみを Blender でレンダリングして PNG を生成する。

    CSV や降水量データは使用しない。国土数値情報 N03 GeoJSON を
    ダウンロード（初回のみ）して Japan の陸地形状を正確に描画する。
    tile_source で指定した国土地理院タイルをベースマップとして使用する。

    Args:
        output_path: 出力 PNG パス。
        engine: レンダーエンジン ('EEVEE' or 'CYCLES')。
        resolution_x/y: 出力解像度。
        samples: レンダーサンプル数。
        timeout: Blender タイムアウト（秒）。
        geojson_url: GeoJSON ダウンロード URL。
        geojson_cache: ローカルキャッシュパス。
        rdp_epsilon: RDP 簡略化許容誤差（度）。小さいほど詳細。
        min_bbox_area: 最小ポリゴン面積フィルタ（deg²）。
        camera_location: カメラ位置。
        camera_rotation: カメラ回転（Euler rad）。
        background_color: ワールド背景 RGBA。
        ocean_color: 海の RGB（テクスチャ未使用時）。
        land_color: 陸地の RGB（テクスチャ未使用時）。
        tile_zoom: タイルのズームレベル（デフォルト 5）。
        tile_source: タイルソース ("std", "pale", "relief", "photo")。None で2色ポリゴン描画。
        force_tile_refresh: True の場合、タイルキャッシュを再ダウンロード。

    Returns:
        Dict: output_path, polygons_count, cache_path, texture_path。

    Raises:
        RuntimeError: Blender が見つからないか描画失敗。
    """
    # GeoJSON 取得
    geojson = fetch_japan_geojson(url=geojson_url, cache_path=geojson_cache)
    land_polygons = extract_japan_polygons(
        geojson, epsilon=rdp_epsilon, min_bbox_area=min_bbox_area
    )
    print(f"陸地ポリゴン数: {len(land_polygons)}")

    # 地図テクスチャ取得（tile_source=None なら2色ポリゴン描画）
    texture_path = None
    if tile_source is not None:
        texture_path = fetch_map_texture(
            zoom=tile_zoom, tile_source=tile_source, force_refresh=force_tile_refresh
        )

    script = generate_japan_map_script(
        land_polygons=land_polygons,
        output_path=output_path,
        engine=engine,
        resolution_x=resolution_x,
        resolution_y=resolution_y,
        samples=samples,
        camera_location=camera_location,
        camera_rotation=camera_rotation,
        camera_type=camera_type,
        camera_lens=camera_lens,
        ortho_zoom=ortho_zoom,
        background_color=background_color,
        ocean_color=ocean_color,
        land_color=land_color,
        texture_path=texture_path,
    )

    result = run_script(script, timeout=timeout)

    if result.returncode != 0:
        raise RuntimeError(
            f"Blender rendering failed (exit {result.returncode}):\n"
            f"STDOUT:\n{result.stdout[-3000:]}\n"
            f"STDERR:\n{result.stderr[-2000:]}"
        )

    cache = geojson_cache or _GEOJSON_CACHE
    return {
        "output_path": output_path,
        "polygons_count": len(land_polygons),
        "cache_path": str(cache),
        "texture_path": str(texture_path) if texture_path else None,
        "script_stdout": result.stdout,
    }
