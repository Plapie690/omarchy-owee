#!/usr/bin/env python3
"""Backend for the Omarchy weather widget. No third-party Python packages."""
import json
import copy
import re
import fcntl
import hashlib
import math
import os
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
sys.dont_write_bytecode = True  # Imports must not trigger Omarchy plugin hot reload.
import notifications
import network
import storage
from weather_data import normalize_weather, normalize_air

LIMIT = 1_000_000
DEFAULT = {"name": "Lyon", "latitude": 45.75, "longitude": 4.85, "country": "France"}
STATE = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "pixel-weather"
WEATHER = "https://api.open-meteo.com/v1/forecast"
GEO = "https://geocoding-api.open-meteo.com/v1/search"
AIR = "https://air-quality-api.open-meteo.com/v1/air-quality"
CARD_IDS = ["wind", "humidity", "uv", "sun", "pressure", "visibility", "precipitation", "air", "pollen"]


read_json = storage.read_json
save_json = storage.save_json
MIN_REFRESH_SECONDS = 60


def request(url, params):
    cooldown_path = STATE / '.weather-backoff.json'
    cooldown = read_json(cooldown_path, {})
    host = url.split('/')[2]
    until = cooldown.get(host, 0) if isinstance(cooldown, dict) else 0
    if type(until) in (int, float) and until > time.time():
        raise network.NetworkError('Provider cooling down', int(until-time.time()))
    try:
        return network.request(url, params)
    except network.NetworkError as error:
        if error.retry_after:
            with storage.lock(STATE / '.backoff.lock'):
                current = read_json(cooldown_path, {})
                if not isinstance(current, dict): current = {}
                current[host] = time.time() + min(900, error.retry_after)
                save_json(cooldown_path, current)
        raise


def location(obj):
    if not isinstance(obj, dict):
        raise ValueError("Invalid city")
    name = str(obj.get("name", "")).strip()[:80]
    if isinstance(obj.get("latitude"), bool) or isinstance(obj.get("longitude"), bool):
        raise ValueError("Invalid coordinates")
    lat, lon = float(obj["latitude"]), float(obj["longitude"])
    if not name or not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("Invalid coordinates")
    return {"name": name, "latitude": lat, "longitude": lon, "country": str(obj.get("country", ""))[:80], "admin1": str(obj.get("admin1", ""))[:80]}


def search(query):
    query = query.strip()[:80]
    if len(query) < 2:
        return {"results": []}
    coordinates = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*,\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))", query)
    if coordinates:
        lat, lon = map(float, coordinates.groups())
        return {"results": [location({"name": f"{lat:.5f}, {lon:.5f}", "latitude": lat, "longitude": lon})]}
    result = request(GEO, {"name": query, "count": 8, "language": "en", "format": "json"})
    found = []
    results = result.get("results", [])
    for city in (results[:8] if isinstance(results, list) else []):
        try:
            found.append(location(city))
        except (KeyError, TypeError, ValueError):
            pass
    return {"results": found}


def forecast(city):
    data = request(WEATHER, {
        "latitude": city["latitude"], "longitude": city["longitude"], "timezone": "auto", "forecast_days": 11, "timeformat": "unixtime",
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,wind_direction_10m,surface_pressure,precipitation,weather_code,is_day",
        "hourly": "temperature_2m,precipitation_probability,weather_code,visibility,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,daylight_duration,uv_index_max,precipitation_probability_max",
    })
    normalized = normalize_weather({**data, "latitude": city["latitude"]})
    air = cached_air(city)
    normalized["air"] = air.get("air", {})
    normalized["air_updated"] = air.get("updated")
    normalized["air_stale"] = air.get("stale", True)
    return {"city": city, "data": normalized, "updated": int(time.time()), "stale": False}


def air_path(city):
    return STATE / ("air-" + hashlib.sha256(city_key(city).encode()).hexdigest()[:16] + ".json")


def cached_air(city):
    cached = read_json(air_path(city), {})
    if not isinstance(cached, dict) or cached.get("city_key") != city_key(city): return {}
    stamp = cached.get("updated")
    if type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp > time.time()+60: return {}
    try: clean = normalize_air({"current": cached.get("air", {})})
    except (ValueError, TypeError): return {}
    return {"city_key": city_key(city), "air": clean["current"], "capabilities": clean["capabilities"], "updated": stamp, "stale": time.time()-stamp>3600}


def enrich(city):
    cached = cached_air(city)
    if cached and not cached["stale"]: return cached
    try:
        with storage.lock(STATE / (".air-"+hashlib.sha256(city_key(city).encode()).hexdigest()[:16]+".lock")):
            raw = request(AIR, {"latitude": city["latitude"], "longitude": city["longitude"], "timezone": "auto", "forecast_days": 1, "current": "european_aqi,pm2_5,alder_pollen,birch_pollen,grass_pollen,mugwort_pollen,olive_pollen,ragweed_pollen"})
            clean = normalize_air(raw)
            result = {"city_key": city_key(city), "air": clean["current"], "capabilities": clean["capabilities"], "updated": int(time.time()), "stale": False}
            save_json(air_path(city), result)
            storage.prune_weather(STATE, [air_path(city), cache_for(city)])
            return result
    except (OSError, ValueError):
        if cached: return {**cached, "stale": True}
        return {"city_key": city_key(city), "air": {}, "capabilities": {"air": {"status": "unavailable", "source": "CAMS / Open-Meteo"}, "pollen": {"status": "unavailable", "source": "CAMS / Open-Meteo"}}, "error": "Air and pollen data unavailable", "stale": True}


def city_key(city):
    return f"{city['latitude']:.5f},{city['longitude']:.5f}"


def cache_for(city):
    return STATE / ("forecast-" + hashlib.sha256(city_key(city).encode()).hexdigest()[:16] + ".json")


def cached_forecast(city):
    """Read only a matching city's valid weather payload, never saved UI metadata."""
    for path in (cache_for(city), STATE / "forecast.json"):
        raw = read_json(path, {})
        if not isinstance(raw, dict):
            continue
        try:
            cached_city = location(raw.get("city"))
            if city_key(cached_city) != city_key(city):
                continue
        except (ValueError, TypeError, KeyError):
            continue
        data = raw.get("data")
        if not isinstance(data, dict):
            continue
        current, hourly, daily = data.get("current"), data.get("hourly"), data.get("daily")
        if not all(isinstance(x, dict) for x in (current, hourly, daily)):
            continue
        temperature = current.get("temperature_2m")
        if type(temperature) not in (int, float) or not -150 <= temperature <= 100:
            continue
        if (not isinstance(hourly.get("time"), list) or len(hourly["time"]) > 500
                or not isinstance(daily.get("time"), list) or len(daily["time"]) > 20):
            continue
        updated = raw.get("updated", 0)
        if type(updated) not in (int, float) or not 0 <= updated <= time.time() + 300:
            updated = 0
        try:
            normalized = normalize_weather({**data, "latitude": city["latitude"]})
        except (ValueError, TypeError, OverflowError):
            continue
        try: normalized["air"] = normalize_air({"current": data.get("air", {})})["current"]
        except (ValueError, TypeError): normalized["air"] = {}
        normalized["air_stale"] = data.get("air_stale", True)
        normalized["air_updated"] = data.get("air_updated")
        return {"city": city, "data": normalized, "updated": updated,
                "stale": raw.get("stale") is True or time.time() - updated > 1800}
    return None


def weather_for(city, *, refresh=False, network=False, required=False):
    """Refresh when requested, with a validated per-city cache as offline fallback."""
    cached = cached_forecast(city)
    if cached and (not refresh or time.time()-cached.get("updated", 0) < MIN_REFRESH_SECONDS):
        return cached
    if network:
        try:
            with storage.lock(STATE / (".forecast-"+hashlib.sha256(city_key(city).encode()).hexdigest()[:16]+".lock")):
                newest = cached_forecast(city)
                if newest and time.time()-newest.get("updated",0) < MIN_REFRESH_SECONDS:
                    return newest
                try:
                    result = forecast(city)
                except Exception:
                    latest = cached_forecast(city)
                    if latest:
                        if cached and latest.get("updated",0)>cached.get("updated",0): return latest
                        latest["stale"] = True
                        save_json(cache_for(city), latest)
                        return latest
                    if required: raise
                    return {"city":city,"stale":True,"error":"Weather connection unavailable"}
                try:
                    save_json(cache_for(city), result)
                    storage.prune_weather(STATE, [cache_for(city)])
                except OSError:
                    result["cache_error"] = "Local cache unavailable; live data is shown"
                return result
        except BlockingIOError:
            if cached: return {**cached,"refresh_pending":True}
            if required: raise OSError("Weather update already in progress; please retry")
        except Exception:
            if cached:
                cached["stale"] = True
                # A failed competing worker must never overwrite a newer cache.
                return cached
            if required:
                raise
    return cached or {"city": city, "error": "Weather connection unavailable", "stale": True}


def main(args):
    action = args[0] if args else "load"
    if action == "search":
        return search(args[1] if len(args) > 1 else "")
    if action == "air":
        return enrich(location(json.loads(args[1])))
    state_path = STATE / "settings.json"
    settings = read_json(state_path, {})
    before_settings = copy.deepcopy(settings) if isinstance(settings, dict) else {}
    if not isinstance(settings, dict):
        settings = {}
    try:
        city = location(settings.get("city", DEFAULT))
    except (ValueError, TypeError, KeyError):
        city = location(DEFAULT)
    cities = []
    raw_cities = settings.get("cities", [])
    if isinstance(raw_cities, list):
        for raw in raw_cities[:30]:
            try:
                item = location(raw)
                if city_key(item) not in [city_key(x) for x in cities]:
                    cities.append(item)
            except (ValueError, TypeError, KeyError):
                pass
    if city_key(city) not in [city_key(x) for x in cities]:
        cities.insert(0, city)
        cities = cities[:30]
    # Existing 0.4 city becomes the primary before any new city is selected.
    try:
        candidate = location(settings.get("primary_city", city))
        primary = next((c for c in cities if city_key(c) == city_key(candidate)), city)
    except (ValueError, TypeError, KeyError):
        primary = city
    migrate_primary = settings.get("primary_city") != primary
    cards = settings.get("cards", CARD_IDS)
    if not isinstance(cards, list):
        cards = CARD_IDS[:]
    cards = list(dict.fromkeys(x for x in cards if isinstance(x, str) and x in CARD_IDS))
    hidden = settings.get("hidden_cards", [])
    if not isinstance(hidden, list):
        hidden = []
    hidden = list(dict.fromkeys(x for x in hidden if isinstance(x, str) and x in CARD_IDS))
    for key in CARD_IDS:
        if key not in cards:
            cards.append(key)
    unit = settings.get("unit", "C")
    if unit not in ("C", "F"):
        unit = "C"
    notification_config = notifications.normalise_settings(settings.get("notifications"))
    if action == "notify-test":
        return {"notification_status": notifications.send_test(primary)}
    if action == "notify":
        if settings.get("auto_refresh", True) is False:
            return {"notification_status": {"sent": 0}}
        cached = cached_forecast(primary) or {"city": primary, "stale": True}
        cached["unit"] = unit
        return {"notification_status": notifications.dispatch(cached, notification_config, STATE)}

    resolved = {}
    if action == "auto":
        settings["auto_refresh"] = len(args) > 1 and args[1] == "on"
    elif action == "unit":
        unit = "F" if len(args) > 1 and args[1] == "F" else "C"
        settings["unit"] = unit
    elif action == "notifications":
        patch = json.loads(args[1])
        if not isinstance(patch, dict):
            raise ValueError("Invalid settings")
        notification_config = notifications.normalise_settings({**notification_config, **patch})
        settings["notifications"] = notification_config
    elif action == "select":
        candidate = location(json.loads(args[1]))
        key = city_key(candidate)
        if key not in [city_key(x) for x in cities] and len(cities) >= 30:
            raise ValueError("Too many cities")
        # No preferences change until the city has live or validated cached weather.
        resolved[key] = weather_for(candidate, refresh=True, network=True, required=True)
        city = candidate
        if city_key(primary) == key:
            primary = city
        if key not in [city_key(x) for x in cities]:
            cities.append(city)
        else:
            cities = [city if city_key(x) == key else x for x in cities]
    elif action == "primary":
        key = args[1]
        candidate = next((c for c in cities if city_key(c) == key), None)
        if candidate is None:
            raise ValueError("Choose a favorite city")
        resolved[key] = weather_for(candidate, network=True, required=True)
        primary = candidate
    elif action == "remove":
        key = str(args[1])
        if len(cities) > 1:
            cities = [c for c in cities if city_key(c) != key]
            if city_key(primary) == key:
                primary = city if city_key(city) != key else cities[0]
            if city_key(city) == key:
                city = primary
    elif action == "move-city":
        obj = json.loads(args[1])
        if not isinstance(obj, dict):
            raise ValueError("Invalid move")
        key, direction = obj.get("key"), obj.get("direction")
        index = next((i for i, c in enumerate(cities) if city_key(c) == key), -1)
        dest = index + (-1 if direction == "up" else 1 if direction == "down" else 0)
        if index >= 0 and 0 <= dest < len(cities):
            cities[index], cities[dest] = cities[dest], cities[index]
    elif action == "cards":
        obj = json.loads(args[1])
        if not isinstance(obj, dict):
            raise ValueError("Invalid card settings")
        key, op = obj.get("id"), obj.get("op")
        if op == "reorder":
            order = obj.get("order")
            if (not isinstance(order, list) or len(order) != len(CARD_IDS)
                    or any(not isinstance(x, str) for x in order)
                    or set(order) != set(CARD_IDS)):
                raise ValueError("Invalid card order")
            cards = order[:]
        elif key in CARD_IDS:
            if op == "toggle":
                hidden = [x for x in hidden if x != key] if key in hidden else hidden + [key]
            elif op in ("up", "down"):
                index = cards.index(key)
                dest = index + (-1 if op == "up" else 1)
                if 0 <= dest < len(cards):
                    cards[index], cards[dest] = cards[dest], cards[index]
    elif action != "load":
        raise ValueError("Unknown action")

    settings.update({"city": city, "primary_city": primary, "cities": cities,
                     "cards": cards, "hidden_cards": hidden})
    if action != "load" or migrate_primary:
        storage.commit_settings(state_path, before_settings, settings)
    # At most two cities are refreshed, and never the same city twice.
    for target in (primary, city):
        key = city_key(target)
        if key not in resolved:
            resolved[key] = weather_for(target, refresh=action == "load" and (len(args)<2 or args[1]!="primary-only" or key==city_key(primary)),
                                       network=action in ("load", "select", "primary") and (action!="load" or len(args)<2 or args[1]!="primary-only" or key==city_key(primary)))
    primary_result = dict(resolved[city_key(primary)])
    primary_result["unit"] = unit
    result = dict(resolved[city_key(city)])
    result.update({"unit": unit, "auto_refresh": settings.get("auto_refresh", True) is not False,
                   "cities": cities, "cards": cards, "hidden_cards": hidden,
                   "notifications": notification_config, "primary_city": primary,
                   "primary": primary_result})
    if action == "load" and result["auto_refresh"]:
        result["notification_status"] = notifications.dispatch(primary_result, notification_config, STATE)
    return result


if __name__ == "__main__":
    try:
        result = main(sys.argv[1:])
        output = json.dumps(result, ensure_ascii=False, allow_nan=False)
    except Exception as error:
        message = str(error)[:160] if isinstance(error, (ValueError, network.NetworkError)) else "Unable to retrieve data. Please try again."
        output = json.dumps({"error": message}, ensure_ascii=False)
    print(output)
