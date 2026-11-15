#!/usr/bin/env python3
"""Opt-in ECCC GDPS forecast maps. One requested WMS viewport at a time.

GeoMet forbids bulk/batch WMS tile retrieval: this module deliberately fetches
only the selected forecast instant. Other instants are advertised, not prefetched.
"""
import fcntl
import storage
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import sys
import tempfile
import time
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import xml.etree.ElementTree as ET
import zlib

sys.dont_write_bytecode = True
import radar

STATE = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "pixel-weather"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "pixel-weather/forecast-map"
WMS_URL = "https://geo.weather.gc.ca/geomet"
USER_AGENT = "OWEE/1.3 (community desktop weather)"
XML_LIMIT = 300_000
JSON_LIMIT = 100_000
IMAGE_LIMIT = 1_000_000
CACHE_BYTES = 64 * 1024 * 1024
CACHE_FILES = 512
WIDTH, HEIGHT = 432, 240
RADIUS = 6378137.0
WORLD_HALF = math.pi * RADIUS
MAX_REFERENCE_AGE = 48 * 3600
CAPS_TTL = 1800
LAYERS = {
    "precipitation": {
        "name": "GDPS_15km_PrecipType-Significant1h", "style": "SIGPRECIPITATIONTYPE",
        "title": "1-hour precipitation", "unit": "mm / 1 h",
        "caption": "Dominant precipitation type and amount over the preceding hour (mm).",
    },
    "temperature": {
        "name": "GDPS_15km_AirTemp_2m", "style": "TEMPERATURE-LINEAR",
        "title": "Temperature at 2 m", "unit": "°C",
        "caption": "Forecast air temperature 2 m above ground (°C).",
    },
    "clouds": {
        "name": "GDPS_15km_TotalCloudCover", "style": "CLOUD",
        "title": "Clouds", "unit": "%",
        "caption": "Forecast total cloud cover (%).",
    },
}


def read_json(path, fallback):
    if path.name.endswith("settings.json"): return storage.read_json(path, fallback)
    try:
        if path.stat().st_size > JSON_LIMIT:
            return fallback
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return fallback


def save_bytes(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".forecast-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_json(path, value):
    if path.name.endswith("settings.json"): return storage.save_json(path, value)
    save_bytes(path, json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))


def settings():
    raw = read_json(STATE / "forecast-map-settings.json", {})
    raw = raw if isinstance(raw, dict) else {}
    return {"enabled": raw.get("enabled") is True,
            "zoom": raw.get("zoom") if type(raw.get("zoom")) is int and 3 <= raw["zoom"] <= 7 else 6,
            "layer": raw.get("layer") if isinstance(raw.get("layer"), str) and raw["layer"] in LAYERS else "precipitation"}


def configure(change):
    with storage.lock(STATE / ".forecast_map-settings.lock"):
        return _configure(change)

def _configure(change):
    if not isinstance(change, dict):
        raise ValueError("Invalid map settings")
    current = settings()
    if "enabled" in change:
        if type(change["enabled"]) is not bool:
            raise ValueError("Invalid activation")
        current["enabled"] = change["enabled"]
    if "zoom" in change:
        if type(change["zoom"]) is not int or not 3 <= change["zoom"] <= 7:
            raise ValueError("Invalid zoom")
        current["zoom"] = change["zoom"]
    if "layer" in change:
        if not isinstance(change["layer"], str) or change["layer"] not in LAYERS:
            raise ValueError("Invalid layer")
        current["layer"] = change["layer"]
    save_json(STATE / "forecast-map-settings.json", current)
    return current


def coordinates(city):
    if not isinstance(city, dict):
        raise ValueError("Invalid city")
    lat, lon = city.get("latitude"), city.get("longitude")
    if (type(lat) not in (int, float) or type(lon) not in (int, float)
            or not -90 <= lat <= 90 or not -180 <= lon <= 180
            or not math.isfinite(lat) or not math.isfinite(lon)):
        raise ValueError("Invalid coordinates")
    return lat, lon


def wms_url(**params):
    return WMS_URL + "?" + urlencode({"SERVICE": "WMS", "VERSION": "1.3.0", **params})


def allowed_url(url):
    parsed = urlsplit(url)
    return parsed.scheme == "https" and parsed.netloc == "geo.weather.gc.ca" and parsed.path in ("/geomet", "/geomet/")


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_url(newurl):
            raise ValueError("Map redirect refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url, limit):
    """A shared nonblocking lock prevents parallel WMS requests from two bars."""
    if not allowed_url(url):
        raise ValueError("Map source refused")
    CACHE.mkdir(parents=True, exist_ok=True)
    with (CACHE / ".network-lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        now = time.time()
        recent = read_json(CACHE / "requests.json", [])
        recent = recent if isinstance(recent, list) else []
        recent = [stamp for stamp in recent[:100] if type(stamp) in (int, float) and now - 60 < stamp <= now]
        if len(recent) >= 24:
            raise OSError("Try again in a minute")
        save_json(CACHE / "requests.json", recent + [now])
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/xml, image/png"})
        with build_opener(SafeRedirect()).open(request, timeout=8) as response:
            result = response.read(limit + 1)
        if len(result) > limit:
            raise ValueError("Map response too large")
        return result


def iso_time(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def timestamp(value):
    if not isinstance(value, str) or len(value) > 32:
        raise ValueError("Invalid map date")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("Invalid map timezone")
    result = int(parsed.timestamp())
    if not 0 <= result <= 10_000_000_000:
        raise ValueError("Invalid map date")
    return result


def time_dimension(text):
    if not isinstance(text, str) or len(text) > 25_000:
        raise ValueError("Invalid time axis")
    result = set()
    pieces_list = text.split(",")
    if len(pieces_list) > 500:
        raise ValueError("Time axis too large")
    for piece in pieces_list:
        pieces = piece.strip().split("/")
        if len(pieces) == 1:
            result.add(timestamp(pieces[0]))
        elif len(pieces) == 3:
            start, end = timestamp(pieces[0]), timestamp(pieces[1])
            duration = re.fullmatch(r"PT(?:(\d{1,3})H)?(?:(\d{1,2})M)?", pieces[2])
            if not duration:
                raise ValueError("Invalid map step")
            step = int(duration[1] or 0) * 3600 + int(duration[2] or 0) * 60
            if step < 3600 or step > 86400 or end < start or (end - start) // step > 500:
                raise ValueError("Time axis too large")
            result.update(range(start, end + 1, step))
        else:
            raise ValueError("Invalid time axis")
        if len(result) > 500:
            raise ValueError("Time axis too large")
    if not result:
        raise ValueError("No forecast time available")
    return sorted(result)


def validate_capabilities(value, now=None):
    now = time.time() if now is None else now
    if (not isinstance(value, dict) or not isinstance(value.get("layer"), str)
            or value["layer"] not in LAYERS):
        raise ValueError("Invalid map metadata")
    reference, times = value.get("reference"), value.get("times")
    if (type(reference) is not int or not now - MAX_REFERENCE_AGE <= reference <= now + 300
            or not isinstance(times, list) or not 1 <= len(times) <= 500
            or any(type(t) is not int or not reference <= t <= reference + 16 * 86400 for t in times)):
        raise ValueError("Expired or invalid forecast")
    return {"layer": value["layer"], "reference": reference, "times": sorted(set(times))}


def parse_capabilities(data, layer_id, now=None):
    if not isinstance(data, bytes) or len(data) > XML_LIMIT or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("Invalid XML metadata")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as error:
        raise ValueError("Invalid XML metadata") from error
    if sum(1 for _ in root.iter()) > 5000:
        raise ValueError("XML metadata too large")
    spec = LAYERS[layer_id]
    layer = next((node for node in root.findall(".//{*}Layer")
                  if node.findtext("{*}Name") == spec["name"]), None)
    if layer is None:
        raise ValueError("Map layer unavailable")
    styles = [node.findtext("{*}Name") for node in layer.findall("{*}Style")]
    if spec["style"] not in styles:
        raise ValueError("Map style unavailable")
    dimensions = {node.get("name", "").lower(): node for node in layer.findall("{*}Dimension")}
    if "time" not in dimensions or "reference_time" not in dimensions:
        raise ValueError("Missing time axis")
    reference = timestamp(dimensions["reference_time"].get("default", ""))
    value = {"layer": layer_id, "reference": reference,
             "times": time_dimension(dimensions["time"].text or "")}
    return validate_capabilities(value, now)


def capabilities(layer_id):
    path = CACHE / ("capabilities-" + layer_id + ".json")
    raw = read_json(path, {})
    try:
        cached = validate_capabilities(raw.get("data")) if isinstance(raw, dict) else None
        if cached and cached["layer"] != layer_id:
            cached = None
    except ValueError:
        cached = None
    fetched = raw.get("fetched", 0) if isinstance(raw, dict) else 0
    fresh = type(fetched) in (int, float) and 0 <= time.time() - fetched < CAPS_TTL
    if cached and fresh:
        return {**cached, "fetched": int(fetched)}, time.time() - cached["reference"] > 30 * 3600
    try:
        result = parse_capabilities(download(wms_url(REQUEST="GetCapabilities", LAYERS=LAYERS[layer_id]["name"]), XML_LIMIT), layer_id)
        fetched = int(time.time())
        save_json(path, {"fetched": fetched, "data": result})
        return {**result, "fetched": fetched}, time.time() - result["reference"] > 30 * 3600
    except (OSError, ValueError):
        if cached:
            return {**cached, "fetched": int(fetched) if type(fetched) in (int, float) and math.isfinite(fetched) else 0}, True
        raise


def future_times(capability, now=None, selected=None):
    now = time.time() if now is None else now
    available = [t for t in capability["times"] if now < t <= now + 24 * 3600]
    if not available:
        raise ValueError("No future forecast available")
    if selected is not None and (type(selected) is not int or selected not in available):
        raise ValueError("Expired or invalid forecast time")
    result = []
    for stamp in available:
        if not result or stamp - result[-1] >= 3 * 3600:
            result.append(stamp)
    if available[-1] not in result:
        result.append(available[-1])
    if selected is not None and selected not in result:
        result.append(selected)
    return sorted(result)[:12]


def viewport_parts(lat, lon, zoom):
    """Same Mercator viewport as radar.viewport, split cleanly at the date line."""
    lat, lon = coordinates({"latitude": lat, "longitude": lon})
    if abs(lat) > radar.MERCATOR_MAX_LATITUDE:
        raise ValueError("Map projection unavailable at this latitude")
    if type(zoom) is not int or not 3 <= zoom <= 7:
        raise ValueError("Invalid map zoom")
    pixels = 256 * 2 ** zoom
    center_x = ((lon + 180) / 360 * pixels) % pixels
    center_y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * pixels
    left, top = center_x - WIDTH / 2, center_y - HEIGHT / 2
    scale = 2 * WORLD_HALF / pixels
    # Clip the image at the projection edge, not the selected location's centre.
    visible_top, visible_bottom = max(0, top), min(pixels, top + HEIGHT)
    visible_height = max(0, visible_bottom-visible_top)
    minimum_y, maximum_y = WORLD_HALF - visible_bottom * scale, WORLD_HALF - visible_top * scale
    remaining, offset, start = WIDTH, 0.0, left % pixels
    parts = []
    while remaining > 0.000001:
        span = min(remaining, pixels - start)
        if span > 0.000001:
            parts.append({"left": offset, "top": visible_top-top, "width": span, "height": visible_height,
                          "pixel_width": max(1, round(span)), "pixel_height": max(1,round(visible_height)),
                          "bbox": [-WORLD_HALF + start * scale, minimum_y,
                                   -WORLD_HALF + (start + span) * scale, maximum_y]})
        offset += span
        remaining -= span
        start = 0.0
    return parts


def png_size(data):
    if not isinstance(data, bytes) or not 45 <= len(data) <= IMAGE_LIMIT or not data.startswith(radar.PNG):
        raise ValueError("Invalid map image")
    offset, width, height, idat, chunks = 8, 0, 0, False, 0
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        if length > IMAGE_LIMIT or offset + length + 12 > len(data):
            raise ValueError("Truncated map image")
        body = data[offset + 8:offset + 8 + length]
        crc = struct.unpack(">I", data[offset + 8 + length:offset + 12 + length])[0]
        if zlib.crc32(kind + body) & 0xffffffff != crc:
            raise ValueError("Corrupted map image")
        if chunks == 0:
            if kind != b"IHDR" or length != 13:
                raise ValueError("Invalid map image")
            width, height = struct.unpack(">II", body[:8])
            if not 1 <= width <= 1024 or not 1 <= height <= 1024:
                raise ValueError("Invalid map dimensions")
        if kind == b"IDAT":
            idat = True
        offset += length + 12
        chunks += 1
        if chunks > 256:
            raise ValueError("Map image too large")
        if kind == b"IEND":
            if length or offset != len(data) or not idat:
                raise ValueError("Invalid map image")
            return width, height
    raise ValueError("Truncated map image")


def image_path(url):
    return CACHE / "images" / (hashlib.sha256(url.encode()).hexdigest() + ".png")


def image(url, expected=None, network=False):
    path = image_path(url)
    try:
        if path.stat().st_size <= IMAGE_LIMIT:
            size = png_size(path.read_bytes())
            if expected is None or size == expected:
                return {"source": path.resolve().as_uri(), "width": size[0], "height": size[1]}, False
    except (OSError, ValueError):
        pass
    if not network:
        return None, False
    try:
        data = download(url, IMAGE_LIMIT)
        size = png_size(data)
        if expected is not None and size != expected:
            raise ValueError("Invalid map dimensions")
        save_bytes(path, data)
        return {"source": path.resolve().as_uri(), "width": size[0], "height": size[1]}, False
    except (OSError, ValueError):
        return None, True


def map_url(layer_id, reference, stamp, part):
    spec = LAYERS[layer_id]
    return wms_url(REQUEST="GetMap", LAYERS=spec["name"], STYLES=spec["style"], CRS="EPSG:3857",
                   BBOX=",".join(f"{number:.6f}" for number in part["bbox"]),
                   WIDTH=part["pixel_width"], HEIGHT=part["pixel_height"], FORMAT="image/png",
                   TRANSPARENT="TRUE", TIME=iso_time(stamp), DIM_REFERENCE_TIME=iso_time(reference))


def legend_url(layer_id):
    spec = LAYERS[layer_id]
    return wms_url(REQUEST="GetLegendGraphic", LAYER=spec["name"], STYLE=spec["style"],
                   SLD_VERSION="1.1.0", FORMAT="image/png", LANG="en")


def prune_cache(protected=()):
    entries = []
    for path in (CACHE / "images").glob("*.png"):
        try:
            stat = path.stat()
            entries.append((stat.st_mtime, path, stat.st_size))
        except OSError:
            pass
    total, count = sum(x[2] for x in entries), len(entries)
    for modified, path, size in sorted(entries):
        if path in protected:
            continue
        if time.time() - modified > 72 * 3600 or total > CACHE_BYTES or count > CACHE_FILES:
            try:
                path.unlink()
                total -= size
                count -= 1
            except OSError:
                pass
    for directory in (CACHE, CACHE / "images"):
        for path in directory.glob(".forecast-*"):
            try:
                if time.time() - path.stat().st_mtime > 300:
                    path.unlink()
            except OSError:
                pass


def empty_result(prefs):
    spec = LAYERS[prefs["layer"]]
    return {"settings": prefs, "width": WIDTH, "height": HEIGHT, "tiles": [], "frames": [],
            "provider": "ECCC GeoMet", "model": "GDPS", "resolution": "15 km",
            "title": spec["title"], "unit": spec["unit"],
            "layers": [{"id": key, "title": layer["title"]} for key, layer in LAYERS.items()],
            "legend": {"source": "", "width": 0, "height": 0, "caption": spec["caption"]},
            "updated": int(time.time()), "stale": False}


def load(city, selected=None):
    prefs = settings()
    result = empty_result(prefs)
    if not prefs["enabled"]:
        return result
    lat, lon = coordinates(city)
    result.update(latitude=lat, longitude=lon)
    if abs(lat) > radar.MERCATOR_MAX_LATITUDE:
        result.update(status="unsupported", reason="projection_limit",
                      capabilities={"forecast_map": {"status": "unsupported", "source": "ECCC GeoMet", "reason": "projection_limit"}},
                      error="Forecast map projection is unavailable beyond 85.05° latitude. The selected location has not moved.")
        return result
    capability, stale = capabilities(prefs["layer"])
    times = future_times(capability, selected=selected)
    selected = times[0] if selected is None else selected
    parts = viewport_parts(lat, lon, prefs["zoom"])
    frames, protected = [], set()
    for stamp in times:
        pieces = []
        for part in parts:
            url = map_url(prefs["layer"], capability["reference"], stamp, part)
            picture, failed = image(url, (part["pixel_width"], part["pixel_height"]),
                                    network=stamp == selected and not stale)
            stale = stale or failed
            if picture:
                protected.add(image_path(url))
                pieces.append({key: part[key] for key in ("left", "top", "width", "height")} | {"source": picture["source"]})
        # Never present a half-map after an interrupted request near the date line.
        frames.append({"time": stamp, "images": pieces if len(pieces) == len(parts) else [],
                       **radar.local_frame_time(stamp, city)})
    base = []
    for tile in radar.viewport(lat, lon, prefs["zoom"]):
        source = radar.tile(f"{radar.OSM_HOST}/{prefs['zoom']}/{tile['x']}/{tile['y']}.png",
                            osm=True, network=not stale)
        base.append({**tile, "source": source or ""})
    legend_address = legend_url(prefs["layer"])
    legend, failed = image(legend_address, network=not stale)
    if legend:
        protected.add(image_path(legend_address))
        result["legend"].update(legend)
    result.update({"tiles": base, "frames": frames, "run_time": capability["reference"],
                   "updated": capability.get("fetched", int(time.time())),
                   "selected_time": selected, "stale": stale, "latitude": lat, "longitude": lon})
    selected_ready = next(bool(frame["images"]) for frame in frames if frame["time"] == selected)
    result["capabilities"] = {"forecast_map": {"status": "available" if selected_ready else "unavailable", "source": "ECCC GeoMet"}}
    model_clock = radar.local_frame_time(capability["reference"], city)
    if model_clock:
        result.update(timezone=model_clock["timezone"], run_local_time=model_clock["local_time"])
    if not next(frame["images"] for frame in frames if frame["time"] == selected):
        result["error"] = "Forecast image unavailable for this time. Please try again."
    elif any(not tile["source"] for tile in base):
        result["message"] = "Some basemap tiles are unavailable."
    if not legend:
        result["message"] = "Legend unavailable; retry before interpreting the colors."
    prune_cache(protected)
    radar.prune_cache()
    return result


def main(args):
    action = args[0] if args else "settings"
    if action == "settings":
        return {"settings": settings()}
    if action == "configure":
        return {"settings": configure(json.loads(args[1]))}
    if action == "load":
        return load(json.loads(args[1]))
    if action == "frame":
        value = json.loads(args[1])
        if not isinstance(value, dict) or type(value.get("time")) is not int:
            raise ValueError("Invalid forecast time")
        return load(value.get("city"), value.get("time"))
    raise ValueError("Unknown map action")


if __name__ == "__main__":
    try:
        output = main(sys.argv[1:])
    except Exception:
        output = empty_result(settings())
        output.update(stale=True, error="Forecast map connection unavailable. Please try again.")
    print(json.dumps(output, ensure_ascii=False, allow_nan=False))
