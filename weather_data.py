"""Bounded Open-Meteo adapters. All authoritative instants are UTC seconds.

Local ISO labels remain available for old UI readers. A legacy ambiguous local
clock label never acquires a guessed UTC instant. Optional malformed readings
become null, while malformed required axes reject the response.
"""
import math
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any, Iterable, Mapping, TypedDict, cast


class WeatherData(TypedDict):
    """Normalized envelope consumed by the QML client; sections allow optional readings."""
    current: dict[str, Any]
    hourly: dict[str, Any]
    daily: dict[str, Any]
    timezone: str
    latitude: float | int | None
    capabilities: dict[str, dict[str, Any]]


class AirData(TypedDict):
    """Optional enrichment envelope, independent of core weather availability."""
    current: dict[str, Any]
    capabilities: dict[str, dict[str, Any]]

MAX_HOURS = 500
MAX_DAYS = 20
WMO_CODES = {0, 1, 2, 3, 45, 48, 51, 53, 55, 56, 57, 61, 63, 65,
             66, 67, 71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 99}
CURRENT_RANGES = {
    "temperature_2m": (-150, 100), "apparent_temperature": (-200, 150),
    "relative_humidity_2m": (0, 100), "wind_speed_10m": (0, 500),
    "wind_direction_10m": (0, 360), "surface_pressure": (1, 1500),
    "precipitation": (0, 10000), "interval": (1, 86400), "is_day": (0, 1),
}
HOURLY_RANGES = {
    "temperature_2m": (-150, 100), "precipitation_probability": (0, 100),
    "visibility": (0, 1000000), "is_day": (0, 1),
}
DAILY_RANGES = {
    "temperature_2m_min": (-150, 100), "temperature_2m_max": (-150, 100),
    "precipitation_probability_max": (0, 100), "uv_index_max": (0, 50),
    "daylight_duration": (0, 86400),
}
POLLEN_FIELDS = ("alder_pollen", "birch_pollen", "grass_pollen", "mugwort_pollen",
                 "olive_pollen", "ragweed_pollen")


def _number(value: object, low: float, high: float, *, integer: bool = False) -> float | int | None:
    if type(value) not in (int, float):
        return None
    number = cast(int | float, value)
    try:
        valid = math.isfinite(number) and low <= number <= high
    except OverflowError:
        return None
    if not valid or (integer and int(number) != number):
        return None
    return int(number) if integer else number


def _zone(value: object) -> ZoneInfo:
    if not isinstance(value, str) or not value or len(value) > 80:
        raise ValueError("Invalid forecast timezone")
    try:
        return ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise ValueError("Invalid forecast timezone") from error


def _local_epoch(parsed: datetime, zone: ZoneInfo) -> int | None:
    if parsed.tzinfo is not None:
        return int(parsed.timestamp())
    candidates = set()
    for fold in (0, 1):
        stamp = parsed.replace(tzinfo=zone, fold=fold).timestamp()
        restored = datetime.fromtimestamp(stamp, zone).replace(tzinfo=None)
        if restored == parsed:
            candidates.add(int(stamp))
    return next(iter(candidates)) if len(candidates) == 1 else None


def _instant(value: object, zone: ZoneInfo) -> tuple[str, int | None]:
    stamp = _number(value, 0, 7258118400)
    if stamp is not None:
        local = datetime.fromtimestamp(stamp, zone)
        return local.replace(tzinfo=None).isoformat(timespec="minutes"), int(stamp)
    if not isinstance(value, str) or not 16 <= len(value) <= 40 or "T" not in value:
        raise ValueError("Invalid forecast timestamp")
    try:
        parsed = datetime.fromisoformat(value)
        if not 1970 <= parsed.year <= 2200:
            raise ValueError("Invalid forecast timestamp")
        stamp = _local_epoch(parsed, zone)
        local = parsed.astimezone(zone) if parsed.tzinfo else parsed
        return local.replace(tzinfo=None).isoformat(timespec="minutes"), stamp
    except (ValueError, OverflowError, OSError) as error:
        raise ValueError("Invalid forecast timestamp") from error


def _axis(value: Any, zone: ZoneInfo, limit: int, *, daily: bool = False) -> tuple[list[str], list[int | None]]:
    if not isinstance(value, list) or not value or len(value) > limit:
        raise ValueError("Invalid or oversized forecast time axis")
    labels, stamps = [], []
    previous = None
    for item in value:
        if daily and isinstance(item, str) and len(item) == 10:
            try:
                parsed = date.fromisoformat(item)
                if not 1970 <= parsed.year <= 2200:
                    raise ValueError("Invalid forecast date")
                label = parsed.isoformat()
            except ValueError as error:
                raise ValueError("Invalid forecast date") from error
            stamp = _local_epoch(datetime.fromisoformat(label), zone)
        else:
            label, stamp = _instant(item, zone)
            if daily:
                label = label[:10]
        if stamp is not None and previous is not None and stamp <= previous:
            raise ValueError("Forecast time axis must be increasing")
        if stamp is not None:
            previous = stamp
        labels.append(label)
        stamps.append(stamp)
    return labels, stamps


def _values(section: Mapping[str, Any], field: str, count: int, limit: int) -> list[Any]:
    value = section.get(field)
    if isinstance(value, list) and len(value) > limit:
        raise ValueError("Oversized forecast field")
    if not isinstance(value, list) or len(value) > count:
        return [None] * count
    return value + [None] * (count - len(value))


def _readings(section: Mapping[str, Any], axes: list[str], ranges: Mapping[str, tuple[int, int]], limit: int) -> dict[str, Any]:
    count = len(axes)
    result = {}
    for field, bounds in ranges.items():
        integer = field == "is_day"
        result[field] = [_number(v, *bounds, integer=integer)
                         for v in _values(section, field, count, limit)]
    result["weather_code"] = [int(v) if type(v) in (int, float) and v in WMO_CODES else None
                              for v in _values(section, "weather_code", count, limit)]
    return result


def _time_axis_source(section: Mapping[str, Any]) -> Any:
    """Use cached UTC instants when both labels and instants are present."""
    labels = section.get("time")
    if "time_utc" not in section:
        return labels
    utc = section["time_utc"]
    if not isinstance(labels, list) or len(labels) > MAX_HOURS or not isinstance(utc, list) or len(utc) != len(labels):
        raise ValueError("Invalid cached UTC time axis")
    return [instant if instant is not None else label for instant, label in zip(utc, labels)]


def _status(values: Iterable[Any]) -> str:
    values = list(values)
    known = sum(value is not None for value in values)
    return "unavailable" if known == 0 else "available" if known == len(values) else "partial"


def _capability(values: Iterable[Any], source: str = "Open-Meteo") -> dict[str, Any]:
    return {"status": _status(values), "source": source}


def _solar_time(value: Any, zone: ZoneInfo) -> tuple[str | None, int | None]:
    if value is None or value == 0:
        return None, None
    try:
        return _instant(value, zone)
    except ValueError:
        return None, None


def normalize_weather(raw: object) -> WeatherData:
    """Return sanitized data, accepting numeric API times and old ISO caches."""
    if not isinstance(raw, dict) or raw.get("error"):
        raise ValueError("Invalid weather response")
    zone = _zone(raw.get("timezone"))
    sections = [raw.get(key) for key in ("current", "hourly", "daily")]
    if not all(isinstance(section, dict) for section in sections):
        raise ValueError("Incomplete forecast")
    current_raw, hourly_raw, daily_raw = cast(tuple[dict[str, Any], dict[str, Any], dict[str, Any]], tuple(sections))
    current: dict[str, Any] = {field: _number(current_raw.get(field), *bounds, integer=field in ("is_day", "interval"))
               for field, bounds in CURRENT_RANGES.items()}
    if current["temperature_2m"] is None:
        raise ValueError("Current temperature unavailable")
    current_time = current_raw.get("time_utc")
    current["time"], current["time_utc"] = _instant(current_raw.get("time") if current_time is None else current_time, zone)
    code = current_raw.get("weather_code")
    current["weather_code"] = int(code) if type(code) in (int, float) and code in WMO_CODES else None
    hour_labels, hour_stamps = _axis(_time_axis_source(hourly_raw), zone, MAX_HOURS)
    day_labels, _ = _axis(daily_raw.get("time"), zone, MAX_DAYS, daily=True)
    hourly = _readings(hourly_raw, hour_labels, HOURLY_RANGES, MAX_HOURS)
    hourly.update(time=hour_labels, time_utc=hour_stamps, rain_intervals=[])
    for end, probability in zip(hour_stamps, hourly["precipitation_probability"]):
        if end is None:
            continue
        start = end - 3600
        start_local, end_local = datetime.fromtimestamp(start, zone), datetime.fromtimestamp(end, zone)
        hourly["rain_intervals"].append({
            "start_utc": start, "end_utc": end,
            "start_local": start_local.replace(tzinfo=None).isoformat(timespec="minutes"),
            "end_local": end_local.replace(tzinfo=None).isoformat(timespec="minutes"),
            "date": start_local.date().isoformat(), "hour": start_local.hour,
            "probability": probability,
            "start_offset": int(cast(timedelta, start_local.utcoffset()).total_seconds()),
            "end_offset": int(cast(timedelta, end_local.utcoffset()).total_seconds()),
        })
    daily = _readings(daily_raw, day_labels, DAILY_RANGES, MAX_DAYS)
    count = len(day_labels)
    solar = {}
    for field in ("sunrise", "sunset"):
        labels = _values(daily_raw, field, count, MAX_DAYS)
        utc = _values(daily_raw, field + "_utc", count, MAX_DAYS)
        solar[field] = [_solar_time(instant if instant is not None else label, zone)
                        for instant, label in zip(utc, labels)]
    daily.update(time=day_labels, solar_state=[])
    for field in ("sunrise", "sunset"):
        daily[field] = [v[0] for v in solar[field]]
        daily[field + "_utc"] = [v[1] for v in solar[field]]
    latitude = _number(raw.get("latitude"), -90, 90)
    for i, duration in enumerate(daily["daylight_duration"]):
        polar = latitude is not None and abs(latitude) >= 66
        if polar and duration in (0, 86400):
            state = "polar_night" if duration == 0 else "polar_day"
            for field in ("sunrise", "sunset", "sunrise_utc", "sunset_utc"):
                daily[field][i] = None
        else:
            rise, setting = daily["sunrise"][i], daily["sunset"][i]
            rise_utc, set_utc = daily["sunrise_utc"][i], daily["sunset_utc"][i]
            ordered = set_utc > rise_utc if rise_utc is not None and set_utc is not None else bool(rise and setting and setting > rise)
            state = "normal" if ordered and duration != 0 else "unavailable"
            if state == "unavailable":
                for field in ("sunrise", "sunset", "sunrise_utc", "sunset_utc"):
                    daily[field][i] = None
        daily["solar_state"].append(state)
    daily = {key: values[:10] for key, values in daily.items()}
    time_capability = _capability([current["time_utc"], *hour_stamps])
    time_capability["precision"] = "utc" if time_capability["status"] == "available" else "legacy_partial"
    return {
        "current": current, "hourly": hourly, "daily": daily, "timezone": zone.key,
        "latitude": latitude,
        "capabilities": {
            "weather": _capability([current["temperature_2m"], *hourly["temperature_2m"], *daily["temperature_2m_min"], *daily["temperature_2m_max"]]),
            "hourly_rain": _capability(hourly["precipitation_probability"]),
            "solar": _capability(None if s == "unavailable" else s for s in daily["solar_state"]),
            "time": time_capability,
        },
    }


def normalize_air(raw: object) -> AirData:
    """Normalize optional CAMS data without inferring geographical coverage."""
    if not isinstance(raw, dict) or raw.get("error") or not isinstance(raw.get("current"), dict):
        raise ValueError("Invalid air-quality response")
    current_raw = raw["current"]
    current: dict[str, Any] = {"european_aqi": _number(current_raw.get("european_aqi"), 0, 1000),
               "pm2_5": _number(current_raw.get("pm2_5"), 0, 5000)}
    current.update({field: _number(current_raw.get(field), 0, 10000000) for field in POLLEN_FIELDS})
    if isinstance(raw.get("timezone"), str) and current_raw.get("time") is not None:
        try:
            current["time"], current["time_utc"] = _instant(current_raw["time"], _zone(raw["timezone"]))
        except ValueError:
            pass
    return {"current": current, "capabilities": {
        "air": _capability([current["european_aqi"], current["pm2_5"]], "CAMS via Open-Meteo"),
        "pollen": _capability([current[field] for field in POLLEN_FIELDS], "CAMS via Open-Meteo"),
    }}
