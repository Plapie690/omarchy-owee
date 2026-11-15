#!/usr/bin/env python3
"""Manual, bounded probes against public sources using public fixture places.

All state is temporary. Missing optional data is recorded, not fabricated;
network/provider errors and source edits invalidate this qualification report.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
from zoneinfo import ZoneInfo

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import weather
from endurance import atomic_json, source_digest, utc_now

PLACES = (
    ("Lyon",45.75,4.85), ("New York",40.71,-74.01), ("Tokyo",35.68,139.69),
    ("Sydney",-33.87,151.21), ("Kathmandu",27.7172,85.324), ("Adelaide",-34.93,138.60),
    ("São Paulo",-23.55,-46.63), ("Nairobi",-1.29,36.82), ("Honolulu",21.31,-157.86),
    ("Tromsø",69.65,18.96), ("Pacific",0,-140), ("North Pole",90,0),
)


def runtime_versions():
    result = subprocess.run(["pacman","-Q","omarchy","quickshell","qt6-base"], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
    return {"python":platform.python_version(), "packages":result.stdout.strip().splitlines()}


def probe(place):
    name, lat, lon = place
    city = {"name":name,"latitude":lat,"longitude":lon}
    result = {"place":name,"latitude":lat,"longitude":lon,"errors":[],"optional_errors":[]}
    try:
        envelope = weather.forecast(city)
        data = envelope["data"]
        zone = ZoneInfo(data["timezone"])
        current = data["current"]
        if type(current["temperature_2m"]) not in (float,int) or not math.isfinite(current["temperature_2m"]):
            raise ValueError("Current temperature is not finite")
        stamp = current.get("time_utc")
        if type(stamp) not in (int,float): raise ValueError("Fresh current UTC instant missing")
        local = datetime.fromtimestamp(stamp,zone).replace(tzinfo=None).isoformat(timespec="minutes")
        if local != current["time"]: raise ValueError("Current UTC and local labels disagree")
        hourly = data["hourly"]
        stamps = hourly.get("time_utc",[])
        if not stamps or len(stamps) != len(hourly["time"]): raise ValueError("Hourly UTC axis missing or misaligned")
        for index, stamp in enumerate(stamps):
            if type(stamp) not in (int,float): raise ValueError("Fresh hourly UTC instant missing")
            local = datetime.fromtimestamp(stamp,zone).replace(tzinfo=None).isoformat(timespec="minutes")
            if local != hourly["time"][index]: raise ValueError("Hourly UTC and local labels disagree")
        for interval in hourly.get("rain_intervals",[]):
            if interval["end_utc"]-interval["start_utc"] != 3600:raise ValueError("Rain interval does not cover one actual hour")
        if not data["daily"]["time"] or len(data["daily"]["time"]) > 10:raise ValueError("Daily horizon invalid")
        duration = data["daily"]["daylight_duration"][0]
        solar = data["daily"]["solar_state"][0]
        if abs(lat)==90 and duration in (0,86400):
            expected = "polar_night" if duration==0 else "polar_day"
            if solar != expected or data["daily"]["sunrise"][0] is not None:raise ValueError("Polar solar state fabricated an event")
        json.dumps(envelope,allow_nan=False)
        result["weather"]={"source":"Open-Meteo","timezone":zone.key,"temperature":current["temperature_2m"],
            "hours":len(stamps),"daily_days":len(data["daily"]["time"]),
            "known_rain_hours":sum(p is not None for p in hourly["precipitation_probability"]),
            "solar_state":solar,"capabilities":data["capabilities"]}
        result["core_passed"]=True
    except Exception as error:
        result["core_passed"]=False;result["errors"].append(str(error)[:250])
    try:
        enrichment = weather.enrich(city)
        result["enrichment"]={"capabilities":enrichment.get("capabilities",{}),
            "aqi":enrichment.get("air",{}).get("european_aqi"),
            "known_pollen_fields":sum(enrichment.get("air",{}).get(key) is not None for key in
                ("alder_pollen","birch_pollen","grass_pollen","mugwort_pollen","olive_pollen","ragweed_pollen")),
            "stale":enrichment.get("stale",True)}
        if enrichment.get("error"):result["optional_errors"].append(enrichment["error"])
    except Exception as error:result["optional_errors"].append(str(error)[:250])
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report",type=Path,default=ROOT/"reports/international.json")
    args=parser.parse_args()
    before,files=source_digest(ROOT); started=utc_now(); clock=time.monotonic()
    previous=weather.STATE
    try:
        with tempfile.TemporaryDirectory(prefix="owee-international-") as temporary:
            weather.STATE=Path(temporary)
            with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(probe,PLACES))
    finally:weather.STATE=previous
    after,_=source_digest(ROOT)
    failures=[r["place"]+": "+error for r in results for error in r["errors"]+r["optional_errors"]]
    if before!=after:failures.append("Source changed during live qualification; rerun on the final commit")
    report={"kind":"international","status":"passed" if not failures else "failed","passed":not failures,
        "started_at":started,"finished_at":utc_now(),"elapsed_seconds":round(time.monotonic()-clock,3),
        "source_sha256":before,"source_sha256_after":after,"source_files":files,
        "runtime":runtime_versions(),"places":results,"core_places_passed":sum(r["core_passed"] for r in results),
        "failures":failures,"personal_state_accessed":False}
    args.report.parent.mkdir(parents=True,exist_ok=True);atomic_json(args.report,report)
    print(json.dumps({"status":report["status"],"core_places_passed":report["core_places_passed"],"places":len(results),"failures":failures},ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
