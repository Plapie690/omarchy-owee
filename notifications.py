"""Opt-in forecast notifications. No network access and no settings mutations.

Schedules use desktop local time; weather hours use the forecast's IANA timezone.
The caller invokes dispatch only after a successful refresh of the selected city.
"""
import fcntl
import hashlib
import html
import json
import math
import os
import re
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from diagnostics import report_error

DEFAULTS = {
    "enabled": False, "rain": True, "rain_probability": 60, "rain_hours": 3,
    "wind": True, "wind_kmh": 50, "uv": True, "uv_index": 6,
    "daily": False, "daily_time": "08:00", "quiet_enabled": True,
    "quiet_start": "22:00", "quiet_end": "07:00", "cooldown_minutes": 180,
}
MAX_AGE = 1800
STATE_LIMIT = 65536


def _number(value, low, high):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and low <= value <= high and math.isfinite(value))


def normalise_settings(config):
    """Return bounded, JSON-safe settings; unknown keys never survive."""
    config = config if isinstance(config, dict) else {}
    output = dict(DEFAULTS)
    for key, default in DEFAULTS.items():
        value = config.get(key, default)
        if isinstance(default, bool):
            output[key] = value if isinstance(value, bool) else default
        elif isinstance(default, str):
            if isinstance(value, str) and re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value):
                output[key] = value
    for key, (low, high) in {
        "rain_probability": (10, 100), "rain_hours": (1, 6),
        "wind_kmh": (5, 150), "uv_index": (1, 15), "cooldown_minutes": (15, 1440),
    }.items():
        value = config.get(key, DEFAULTS[key])
        if _number(value, -1_000_000, 1_000_000):
            output[key] = min(high, max(low, int(value)))
    return output


def _local_now(now=None):
    if isinstance(now, datetime):
        return now.astimezone()
    if now is None:
        return datetime.now().astimezone()
    if not _number(now, 0, 10_000_000_000):
        raise ValueError("Invalid notification clock")
    return datetime.fromtimestamp(now).astimezone()


def _minutes(value):
    return int(value[:2]) * 60 + int(value[3:])


def _quiet(config, clock):
    if not config["quiet_enabled"]:
        return False
    start, end = _minutes(config["quiet_start"]), _minutes(config["quiet_end"])
    minute = clock.hour * 60 + clock.minute
    if start == end:
        return False
    return start <= minute < end if start < end else minute >= start or minute < end


def _parse_time(value, timezone):
    if _number(value, 0, 10_000_000_000):
        try: return datetime.fromtimestamp(value, timezone)
        except (ValueError, OverflowError, OSError): return None
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=timezone) if parsed.tzinfo is None else parsed.astimezone(timezone)
    except (ValueError, OverflowError):
        return None


def _text(value, limit=80):
    """Remove control characters before the notification daemon sees user text."""
    if not isinstance(value, str):
        return ""
    return "".join(c for c in value[:limit] if c.isprintable()).strip()


def _at(values, index):
    return values[index] if isinstance(values, list) and 0 <= index < len(values) else None


def _temperature(value, unit):
    if not _number(value, -100, 70):
        return "—"
    return str(round(value * 9 / 5 + 32 if unit == "F" else value)) + "°" + unit


def _daily_occurrence(clock, schedule):
    """Return the last scheduled local occurrence and its real elapsed age."""
    scheduled = clock.replace(hour=int(schedule[:2]), minute=int(schedule[3:]),
                              second=0, microsecond=0)
    if scheduled.timestamp() > clock.timestamp():
        scheduled -= timedelta(days=1)
    return scheduled, clock.timestamp() - scheduled.timestamp()


def evaluate(result, config, now=None):
    """Return at most four plain-text candidates; no side effects.

    A fresh download timestamp AND a recent observation timestamp are required.
    The daily bulletin is eligible for one hour after its configured local time.
    """
    config = normalise_settings(config)
    clock = _local_now(now)
    if not config["enabled"] or _quiet(config, clock) or not isinstance(result, dict):
        return []
    if result.get("stale") or result.get("error"):
        return []
    stamp = result.get("updated")
    epoch = clock.timestamp()
    if not _number(stamp, epoch - MAX_AGE, epoch + 60):
        return []
    data = result.get("data")
    city = result.get("city")
    if not isinstance(data, dict) or not isinstance(city, dict):
        return []
    if not _number(city.get("latitude"), -90, 90) or not _number(city.get("longitude"), -180, 180):
        return []
    name = _text(city.get("name"))
    if not name:
        return []
    try:
        timezone = ZoneInfo(data.get("timezone", ""))
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        return []
    current = data.get("current")
    if not isinstance(current, dict):
        return []
    current_time = _parse_time(current.get("time_utc", current.get("time")), timezone)
    if current_time is None or not epoch - 5400 <= current_time.timestamp() <= epoch + 300:
        return []
    city_now = clock.astimezone(timezone)
    day = city_now.date().isoformat()
    city_hash = hashlib.sha256(f"{city['latitude']:.5f},{city['longitude']:.5f}".encode()).hexdigest()[:20]
    output = []

    def candidate(kind, title, body, signature):
        output.append({"kind": kind, "title": title, "body": body,
                       "key": city_hash + ":" + kind, "signature": signature[:80]})

    hourly = data.get("hourly", {})
    if config["rain"] and isinstance(hourly, dict) and isinstance(hourly.get("time"), list):
        for index, raw_time in enumerate(hourly["time"][:500]):
            utc = hourly.get("time_utc")
            hour = _parse_time(_at(utc, index) if isinstance(utc, list) else raw_time, timezone)
            chance = _at(hourly.get("precipitation_probability"), index)
            if (hour and epoch < hour.timestamp() <= epoch + config["rain_hours"] * 3600
                    and _number(chance, config["rain_probability"], 100)):
                start = datetime.fromtimestamp(hour.timestamp()-3600, timezone)
                clock_format = "%d/%m %H:%M" if start.date()!=hour.date() else "%H:%M"
                period = start.strftime(clock_format)+"–"+hour.strftime(clock_format)
                if start.utcoffset()!=hour.utcoffset(): period=start.strftime("%H:%M UTC%z")+"–"+hour.strftime("%H:%M UTC%z")
                candidate("rain", "Precipitation in " + name,
                          f"Chance {round(chance)} % during {period} (city local time). Open-Meteo forecast.",
                          hour.isoformat())
                break

    wind = current.get("wind_speed_10m")
    if config["wind"] and _number(wind, config["wind_kmh"], 500):
        candidate("wind", "Strong wind in " + name,
                  f"Current wind: {round(wind)} km/h. Threshold: {config['wind_kmh']} km/h. Open-Meteo data.",
                  current_time.isoformat())

    daily = data.get("daily", {})
    daily_index = -1
    if isinstance(daily, dict) and isinstance(daily.get("time"), list):
        daily_index = next((i for i, value in enumerate(daily["time"][:20]) if value == day), -1)
    uv = _at(daily.get("uv_index_max"), daily_index) if isinstance(daily, dict) else None
    if config["uv"] and _number(uv, config["uv_index"], 30):
        candidate("uv", "UV index in " + name,
                  f"Forecast maximum today: {uv:g}. Threshold: {config['uv_index']}. Open-Meteo forecast.", day)

    scheduled, scheduled_age = _daily_occurrence(clock, config['daily_time'])
    if config["daily"] and 0 <= scheduled_age < 3600:
        unit = "F" if result.get("unit") == "F" else "C"
        low = _temperature(_at(daily.get("temperature_2m_min"), daily_index), unit) if isinstance(daily, dict) else "—"
        high = _temperature(_at(daily.get("temperature_2m_max"), daily_index), unit) if isinstance(daily, dict) else "—"
        candidate("daily", "Daily weather · " + name,
                  f"Currently {_temperature(current.get('temperature_2m'), unit)}. Low {low}, high {high}. Open-Meteo forecast.",
                  scheduled.date().isoformat())
    return output


def _send(title, body):
    # The shell's notification Text may use AutoText: neutralize both sinks.
    title = html.escape(_text(title, 160), quote=True)
    body = html.escape(_text(body, 600), quote=True)
    subprocess.run(["notify-send", "--app-name=OWEE", "--icon=weather-showers-symbolic",
                    "--expire-time=10000", "--", title, body],
                   check=True, timeout=3, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def send_test(city=None):
    """Send an explicitly requested test, even when automatic rules are off."""
    name = _text(city.get("name")) if isinstance(city, dict) else ""
    try:
        _send("OWEE · test", "Notifications are working" + (" for " + name if name else "") + ".")
        return {"sent": 1}
    except (OSError, subprocess.SubprocessError) as error:
        report_error('notifications.test_delivery', error)
        return {"sent": 0, "error": "Unable to send notification: check the notification service."}


def _read_records(path, epoch):
    try:
        if path.stat().st_size > STATE_LIMIT:
            return {}
        records = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(records, dict):
        return {}
    clean = {}
    for key, entry in list(records.items())[:120]:
        if (isinstance(key, str) and re.fullmatch(r"[0-9a-f]{20}:(?:rain|wind|uv|daily)", key)
                and isinstance(entry, dict) and _number(entry.get("sent"), epoch - 14 * 86400, epoch + 60)
                and isinstance(entry.get("signature"), str) and len(entry["signature"]) <= 80):
            clean[key] = {"sent": entry["sent"], "signature": entry["signature"]}
    return clean


def _save_records(path, records):
    # The supported 30 cities need at most 120 entries; trim newest first.
    records = dict(sorted(records.items(), key=lambda pair: pair[1]["sent"], reverse=True)[:120])
    fd, temporary = tempfile.mkstemp(prefix=".notifications-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(records, output, allow_nan=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def dispatch(result, config, state_dir, now=None):
    """Attempt each reserved candidate at most once across processes/reloads.

    Reserve durably before invoking the external notification daemon. A failed
    or interrupted delivery retains its reservation: an alert can be missed,
    but an ambiguous delivery cannot cause duplicate retries.
    """
    config = normalise_settings(config)
    clock = _local_now(now)
    candidates = evaluate(result, config, clock)
    if not candidates:
        return {"sent": 0}
    sent = 0
    operation = 'notifications.state'
    try:
        state_dir = Path(state_dir)
        state_dir.mkdir(parents=True, exist_ok=True)
        with (state_dir / "notifications.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {"sent": 0}
            state_path = state_dir / "notification-state.json"
            epoch = clock.timestamp()
            records = _read_records(state_path, epoch)
            for item in candidates:
                previous = records.get(item["key"], {})
                age = epoch - previous.get("sent", 0)
                if previous and (age < config["cooldown_minutes"] * 60 or previous.get("signature") == item["signature"]):
                    continue
                records[item["key"]] = {"sent": epoch, "signature": item["signature"]}
                operation = 'notifications.reservation'
                _save_records(state_path, records)
                operation = 'notifications.delivery'
                _send(item["title"], item["body"])
                sent += 1
        return {"sent": sent}
    except (OSError, subprocess.SubprocessError) as error:
        report_error(operation, error)
        message = ("Unable to send notification: check the notification service."
                   if operation == 'notifications.delivery' else
                   "Unable to save notification history; no further notifications were sent.")
        return {"sent": sent, "error": message}
