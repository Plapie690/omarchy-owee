#!/usr/bin/env python3
"""On-demand RainViewer radar and OSM viewport tiles; Python standard library only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import storage
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import sys
import tempfile
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from image_validation import PNG as PNG, png_size

STATE = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "pixel-weather"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "pixel-weather/radar"
MANIFEST_URL = "https://api.rainviewer.com/public/weather-maps.json"
RADAR_HOST = "https://tilecache.rainviewer.com"
OSM_HOST = "https://tile.openstreetmap.org"
USER_AGENT = "OWEE/1.3 (community desktop weather)"
MERCATOR_MAX_LATITUDE = 85.05112878
JSON_LIMIT = 65_536
IMAGE_LIMIT = 1_000_000
MAX_CACHE_BYTES = 96 * 1024 * 1024
OSM_CACHE_BYTES = 32 * 1024 * 1024
RATE_LOCK = threading.Lock()
REQUEST_SECONDS = 40
_deadline = None


@contextmanager
def request_budget():
    """Share one monotonic budget across metadata, imagery and basemap workers."""
    global _deadline
    previous = _deadline
    _deadline = min(previous, time.monotonic() + REQUEST_SECONDS) if previous is not None else time.monotonic() + REQUEST_SECONDS
    try:
        yield
    finally:
        _deadline = previous


def remaining_timeout(idle):
    remaining = REQUEST_SECONDS if _deadline is None else _deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Map request timed out")
    return min(idle, remaining)


def read_response(response, limit):
    """Read available chunks rather than allowing a slow drip to reset the budget."""
    output = bytearray()
    while len(output) <= limit:
        timeout = remaining_timeout(8)
        socket = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
        if socket is not None:
            socket.settimeout(timeout)
        block = getattr(response, "read1", response.read)(min(65_536, limit + 1 - len(output)))
        if not block:
            break
        output.extend(block)
    remaining_timeout(8)
    if len(output) > limit:
        raise ValueError("Map response too large")
    return bytes(output)


@contextmanager
def file_lock(file):
    while True:
        remaining_timeout(8)
        try:
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            time.sleep(min(0.01, remaining_timeout(8)))
    try:
        yield
    finally:
        fcntl.flock(file, fcntl.LOCK_UN)


def bounded_cli(callback, fallback):
    """The CLI also bounds stalled DNS and non-interruptible worker shutdown."""
    def expired(signum, frame):
        output = fallback()
        output.update(stale=True, error="Map request timed out. Please try again.")
        print(json.dumps(output, ensure_ascii=False, allow_nan=False), flush=True)
        os._exit(124)
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, REQUEST_SECONDS)
    try:
        return callback()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


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
    fd, tmp = tempfile.mkstemp(prefix=".radar-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(content)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def save_json(path, value):
    if path.name.endswith("settings.json"): return storage.save_json(path, value)
    save_bytes(path, json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))


def settings():
    raw = read_json(STATE / "radar-settings.json", {})
    if not isinstance(raw, dict):
        raw = {}
    zoom = raw.get("zoom", 6)
    return {"enabled": raw.get("enabled") is True,
            "zoom": zoom if type(zoom) is int and 3 <= zoom <= 7 else 6}


def configure(value):
    with storage.lock(STATE / ".radar-settings.lock"):
        return _configure(value)

def _configure(value):
    if not isinstance(value, dict):
        raise ValueError("Invalid radar setting")
    current = settings()
    if "enabled" in value:
        if type(value["enabled"]) is not bool:
            raise ValueError("Invalid radar activation")
        current["enabled"] = value["enabled"]
    if "zoom" in value:
        if type(value["zoom"]) is not int or not 3 <= value["zoom"] <= 7:
            raise ValueError("Invalid radar zoom")
        current["zoom"] = value["zoom"]
    save_json(STATE / "radar-settings.json", current)
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


def local_frame_time(stamp, city):
    """Only label frames when the chosen location provides a valid IANA zone."""
    zone = city.get("timezone") if isinstance(city, dict) else None
    if not isinstance(zone, str) or not 0 < len(zone) <= 80:
        return {}
    try:
        clock = datetime.fromtimestamp(stamp, ZoneInfo(zone))
    except (ValueError, OverflowError, OSError, ZoneInfoNotFoundError):
        return {}
    return {"local_time": clock.isoformat(timespec="minutes"), "timezone": zone}


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        if parsed.scheme != "https" or parsed.netloc not in {
                "api.rainviewer.com", "tilecache.rainviewer.com", "tile.openstreetmap.org"}:
            raise ValueError("Radar redirect refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@contextmanager
def rate_guard():
    # Shared across threads and short-lived processes; waits share the request budget.
    CACHE.mkdir(parents=True, exist_ok=True)
    if not RATE_LOCK.acquire(timeout=remaining_timeout(8)):
        raise TimeoutError("Map rate lock timed out")
    try:
        with (CACHE / ".request-lock").open("a") as lock, file_lock(lock):
            now = time.time()
            recent = read_json(CACHE / "requests.json", [])
            if not isinstance(recent, list):
                recent = []
            recent = [t for t in recent if type(t) in (float, int) and now - 60 < t <= now]
            if len(recent) >= 90:
                raise OSError("Radar rate limit reached; try again in a minute")
            save_json(CACHE / "requests.json", recent + [now])
            yield
    finally:
        RATE_LOCK.release()


def download(url, limit):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc not in {
            "api.rainviewer.com", "tilecache.rainviewer.com", "tile.openstreetmap.org"}:
        raise ValueError("Radar source refused")
    with rate_guard():
        pass
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/png, application/json"})
    with build_opener(SafeRedirect()).open(req, timeout=remaining_timeout(5)) as response:
        return read_response(response, limit)


def valid_png(data, size=256):
    try:
        return png_size(data) == (size, size)
    except ValueError:
        return False


def validate_manifest(value, now=None):
    now = time.time() if now is None else now
    if not isinstance(value, dict) or value.get("host") != RADAR_HOST:
        raise ValueError("Invalid radar tile source")
    radar = value.get("radar")
    frames = radar.get("past") if isinstance(radar, dict) else None
    if not isinstance(frames, list) or len(frames) > 24:
        raise ValueError("Invalid radar sequence")
    found = {}
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        stamp, path = frame.get("time"), frame.get("path")
        if type(stamp) is not int or not now - 86400 <= stamp <= now + 300:
            continue
        # Live manifests use opaque frame tokens as well as numeric identifiers.
        if not isinstance(path, str) or not re.fullmatch(r"/v2/radar/[A-Za-z0-9_-]{1,80}", path):
            continue
        found[stamp] = {"time": stamp, "path": path}
    if not found:
        raise ValueError("No recent radar image")
    return {"host": RADAR_HOST, "radar": {"past": [found[t] for t in sorted(found)[-13:]]}}


def manifest():
    path = CACHE / "manifest.json"
    saved = read_json(path, {})
    try:
        cached = validate_manifest(saved)
    except ValueError:
        cached = None
    if cached and time.time() - path.stat().st_mtime < 300:
        return cached, time.time() - cached["radar"]["past"][-1]["time"] > 1800
    try:
        result = validate_manifest(json.loads(download(MANIFEST_URL, JSON_LIMIT)))
        save_json(path, result)
        return result, time.time() - result["radar"]["past"][-1]["time"] > 1800
    except (OSError, ValueError):
        if cached:
            return cached, True
        raise


def viewport(lat, lon, zoom, width=432, height=240):
    """Only valid tiles intersecting the viewport; keep the selected point centred."""
    lat, lon = coordinates({"latitude": lat, "longitude": lon})
    if abs(lat) > MERCATOR_MAX_LATITUDE:
        raise ValueError("Map projection unavailable at this latitude")
    if (type(zoom) is not int or not 3 <= zoom <= 7
            or type(width) is not int or type(height) is not int
            or not 1 <= width <= 1024 or not 1 <= height <= 1024):
        raise ValueError("Invalid map viewport")
    count = 2 ** zoom
    x = ((lon + 180) / 360 * count) % count
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * count
    left, top = x * 256 - width / 2, y * 256 - height / 2
    result = []
    for row in range(math.floor(top / 256), math.ceil((top + height) / 256)):
        for column in range(math.floor(left / 256), math.ceil((left + width) / 256)):
            if 0 <= row < count:
                result.append({"x": column % count, "y": row,
                               "left": column * 256 - left, "top": row * 256 - top})
    return result


def osm_room(preserve):
    """Reserve one bounded response without evicting OSM tiles younger than 7 days."""
    entries = []
    for path in (CACHE / "osm-").glob("*.png"):
        try:
            stat = path.stat()
            entries.append((stat.st_mtime, path, stat.st_size))
        except OSError:
            continue
    total = sum(item[2] for item in entries)
    for modified, path, size in sorted(entries):
        if total + IMAGE_LIMIT <= OSM_CACHE_BYTES:
            break
        if path != preserve and time.time() - modified >= 7 * 86400:
            try:
                path.unlink()
                total -= size
            except OSError:
                pass
    return total + IMAGE_LIMIT <= OSM_CACHE_BYTES


def _tile(url, osm=False, network=True, deadline=None):
    digest = hashlib.sha256(url.encode()).hexdigest()
    coverage = url.startswith(RADAR_HOST + "/v2/coverage/")
    path = CACHE / ("osm-" if osm else "coverage-" if coverage else "radar-") / (digest + ".png")
    cached = None
    try:
        if path.stat().st_size <= IMAGE_LIMIT:
            data = path.read_bytes()
            if valid_png(data):
                cached = path.resolve().as_uri()
                if time.time() - path.stat().st_mtime < (7 * 86400 if osm or coverage else 86400):
                    return cached
    except OSError:
        pass
    if not network or (deadline is not None and time.monotonic() > deadline):
        return cached
    if osm and not osm_room(path):
        return cached  # Refuse a new request rather than repeatedly fetch/evict protected tiles.
    try:
        data = download(url, IMAGE_LIMIT)
        if not valid_png(data):
            raise ValueError("Invalid radar image")
        save_bytes(path, data)
        return path.resolve().as_uri()
    except (OSError, ValueError):
        return cached


def tile(url, osm=False, network=True, deadline=None):
    if not osm:
        return _tile(url, False, network, deadline)
    CACHE.mkdir(parents=True, exist_ok=True)
    # Serialize quota reservation and write, including across simultaneous shell instances.
    with (CACHE / ".osm-cache-lock").open("a") as lock, file_lock(lock):
        return _tile(url, True, network, deadline)


def prune_cache(protected=()):
    """Bound disk usage without prematurely re-fetching recently viewed OSM tiles."""
    CACHE.mkdir(parents=True, exist_ok=True)
    entries = []
    protected = set(protected)
    for folder in (CACHE / "osm-", CACHE / "radar-", CACHE / "coverage-"):
        if not folder.exists():
            continue
        for path in folder.glob("*.png"):
            try:
                stat = path.stat()
                entries.append((stat.st_mtime, path, stat.st_size))
            except OSError:
                continue
    total = sum(item[2] for item in entries)
    # Radar imagery is expendable before a map tile's minimum cache lifetime.
    for modified, path, size in sorted(entries, key=lambda item: (item[1].parent.name == "osm-", item[0])):
        age = time.time() - modified
        keep = path in protected or (path.parent.name == "osm-" and age < 7 * 86400)
        lifetime = 30 * 86400 if path.parent.name == "osm-" else 7 * 86400 if path.parent.name == "coverage-" else 86400
        if not keep and (age > lifetime or total > MAX_CACHE_BYTES):
            try:
                path.unlink()
                total -= size
            except OSError:
                pass


@request_budget()
def load(city):
    prefs = settings()
    if not prefs["enabled"]:
        return {"settings": prefs, "frames": [], "tiles": []}
    lat, lon = coordinates(city)
    if abs(lat) > MERCATOR_MAX_LATITUDE:
        return {"settings": prefs, "latitude": lat, "longitude": lon,
                "tiles": [], "frames": [], "coverage_tiles": [], "coverage_status": "unsupported",
                "status": "unsupported", "reason": "projection_limit",
                "capabilities": {"radar": {"status": "unsupported", "source": "RainViewer", "reason": "projection_limit"}},
                "error": "Radar map projection is unavailable beyond 85.05° latitude. The selected location has not moved."}
    zoom = prefs["zoom"]
    layout = viewport(lat, lon, zoom)
    value, stale = manifest()
    frames = value["radar"]["past"]
    deadline = _deadline
    jobs = [("base", i, f"{OSM_HOST}/{zoom}/{t['x']}/{t['y']}.png", True)
            for i, t in enumerate(layout)]
    jobs.extend(("coverage", i, f"{RADAR_HOST}/v2/coverage/0/256/{zoom}/{t['x']}/{t['y']}/0/0_0.png", False)
                for i, t in enumerate(layout))
    # Prioritise the newest observation if the bounded request budget is exhausted.
    for frame_index in range(len(frames)-1, -1, -1):
        frame = frames[frame_index]
        for i, t in enumerate(layout):
            jobs.append((frame_index, i, f"{RADAR_HOST}{frame['path']}/256/{zoom}/{t['x']}/{t['y']}/2/1_0.png", False))
    def fetch(job):
        group, index, url, osm = job
        return group, index, tile(url, osm, not stale, deadline)
    images = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for group, index, source in pool.map(fetch, jobs):
            images[group, index] = source
    base = [dict(t, source=images.get(("base", i)) or "") for i, t in enumerate(layout)]
    ready = []
    for fi, frame in enumerate(frames):
        if all(images.get((fi, i)) for i in range(len(layout))):
            ready.append({"time": frame["time"], "tiles": [images[fi, i] for i in range(len(layout))],
                          **local_frame_time(frame["time"], city)})
    from urllib.parse import unquote
    protected = {Path(unquote(urlsplit(source).path)) for source in images.values() if source}
    prune_cache(protected)
    result = {"settings": prefs, "latitude": lat, "longitude": lon, "tiles": base,
              "frames": ready, "stale": stale, "width": 432, "height": 240,
              "partial": len(ready) < len(frames) or any(not t["source"] for t in base)}
    coverage = [dict(t, source=images.get(("coverage", i)) or "") for i, t in enumerate(layout)]
    result.update(coverage_tiles=coverage,
                  coverage_status="available" if all(t["source"] for t in coverage) else "unknown",
                  provider="RainViewer")
    # A downloaded mask is evidence of coverage metadata, never evidence of dry weather.
    result["capabilities"] = {"radar": {"status": ("partial" if result["partial"] else "available") if ready else "unavailable", "source": "RainViewer"}}
    if ready and ready[0].get("timezone"):
        result["timezone"] = ready[0]["timezone"]
    if not ready:
        result["error"] = "Radar unavailable. Try again in a minute."
    elif result["partial"]:
        result["message"] = "Some images or tiles are unavailable."
    return result


def main(args):
    action = args[0] if args else "settings"
    if action == "settings":
        return {"settings": settings()}
    if action == "configure":
        return {"settings": configure(json.loads(args[1]))}
    if action == "load":
        return load(json.loads(args[1]))
    raise ValueError("Unknown radar action")


if __name__ == "__main__":
    try:
        output = bounded_cli(lambda: main(sys.argv[1:]), lambda: {"settings": settings(), "frames": []})
    except Exception:
        output = {"settings": settings(), "frames": [], "error": "Radar connection unavailable. Please try again."}
    print(json.dumps(output, ensure_ascii=False, allow_nan=False))
