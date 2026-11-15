#!/usr/bin/env python3
"""Manual live-source cartography gate, with no personal state and a 30s deadline.

Only one forecast time is requested per layer/place. Radar uses one coverage
mask rather than preloading an animation. Projection limits are tested honestly.
"""
import argparse
import json
from pathlib import Path
import signal
import sys
import tempfile
import time
from urllib.parse import parse_qs,unquote,urlsplit

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(HERE))
import forecast_map as forecast
import radar
from endurance import atomic_json,source_digest,utc_now
from international import runtime_versions

LYON={"name":"Lyon","latitude":45.75,"longitude":4.85,"timezone":"Europe/Paris"}
PACIFIC={"name":"Pacific","latitude":0,"longitude":-140,"timezone":"Etc/GMT+9"}
POLE={"name":"North Pole","latitude":90,"longitude":0,"timezone":"Etc/GMT"}


class ProbeDeadline(BaseException):pass


def alarm(*_):raise ProbeDeadline("Global live-map probe deadline exceeded (30 seconds)")


def local_png(uri):
    parsed=urlsplit(uri)
    if parsed.scheme!="file" or parsed.netloc:raise ValueError("Expected a local validated map image")
    return Path(unquote(parsed.path)).read_bytes()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report",type=Path,default=ROOT/"reports/live-maps.json")
    args=parser.parse_args()
    before,files=source_digest(ROOT);started=utc_now();clock=time.monotonic()
    records=[];failures=[];requests=[]
    original=(radar.STATE,radar.CACHE,forecast.STATE,forecast.CACHE,forecast.download)
    previous_handler=signal.signal(signal.SIGALRM,alarm)
    signal.setitimer(signal.ITIMER_REAL,30)
    try:
        with tempfile.TemporaryDirectory(prefix="owee-live-maps-") as temporary:
            base=Path(temporary)
            radar.STATE=forecast.STATE=base/"state"
            radar.CACHE=base/"cache/radar";forecast.CACHE=base/"cache/forecast"
            radar.configure({"enabled":True,"zoom":3})
            forecast.configure({"enabled":True,"zoom":3,"layer":"precipitation"})
            for provider,loader in (("RainViewer",radar.load),("ECCC GeoMet",forecast.load)):
                result=loader(POLE)
                valid=result.get("status")=="unsupported" and result.get("reason")=="projection_limit" and result.get("latitude")==90
                records.append({"place":"North Pole","provider":provider,"status":result.get("status"),"selected_point_preserved":valid})
                if not valid:failures.append(provider+": polar projection limit moved or misrepresented the selected point")
            try:
                manifest,stale=radar.manifest()
                frames=manifest["radar"]["past"]
                uri=radar.tile(f"{radar.RADAR_HOST}/v2/coverage/0/256/3/{LYON['latitude']}/{LYON['longitude']}/0/0_0.png")
                if not uri or not radar.valid_png(local_png(uri)):raise ValueError("Radar coverage mask unavailable or invalid")
                if stale:raise ValueError("Radar manifest is stale")
                records.append({"place":"Lyon","provider":"RainViewer","status":"passed","past_frames":len(frames),
                    "coverage_mask_png_verified":True,"coverage_interpretation":"Mask obtained; this does not imply dry weather"})
            except Exception as error:failures.append("RainViewer: "+str(error)[:250])
            def observed_download(url,limit):
                query=parse_qs(urlsplit(url).query)
                requests.append({key:query.get(key,[]) for key in ("REQUEST","LAYERS","TIME")})
                return original[4](url,limit)
            forecast.download=observed_download
            cases=[(LYON,layer) for layer in forecast.LAYERS]+[(PACIFIC,"precipitation")]
            for city,layer in cases:
                record={"place":city["name"],"layer":layer,"provider":"ECCC GeoMet"}
                try:
                    start=len(requests)
                    forecast.configure({"enabled":True,"zoom":3,"layer":layer})
                    result=forecast.load(city)
                    selected=next(frame for frame in result["frames"] if frame["time"]==result["selected_time"])
                    if not selected["images"]:raise ValueError(result.get("error","Selected forecast image unavailable"))
                    sizes=[forecast.png_size(local_png(piece["source"])) for piece in selected["images"]]
                    legend=result["legend"]
                    if not legend.get("source"):raise ValueError("Forecast legend unavailable")
                    legend_size=forecast.png_size(local_png(legend["source"]))
                    query=parse_qs(urlsplit(forecast.legend_url(layer)).query)
                    if query.get("LANG")!=["en"]:raise ValueError("Legend language is not English")
                    map_requests=[r for r in requests[start:] if r["REQUEST"]==["GetMap"]]
                    distinct_times={tuple(r["TIME"]) for r in map_requests}
                    if len(distinct_times)>1:raise ValueError("More than one forecast time downloaded")
                    record.update(status="passed",png_sizes=sizes,legend_size=legend_size,
                        forecast_times_downloaded=len(distinct_times),frame_time=selected["time"],stale=result["stale"],
                        capabilities=result.get("capabilities"),basemap_available=all(tile.get("source") for tile in result["tiles"]))
                    if result["stale"]:raise ValueError("Selected forecast is stale or incomplete")
                    if not record["basemap_available"]:raise ValueError("OpenStreetMap basemap incomplete")
                except Exception as error:
                    record.update(status="failed",error=str(error)[:250]);failures.append(city["name"]+"/"+layer+": "+str(error)[:250])
                records.append(record)
    except ProbeDeadline as error:failures.append(str(error))
    except Exception as error:failures.append("Probe setup: "+str(error)[:250])
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous_handler)
        radar.STATE,radar.CACHE,forecast.STATE,forecast.CACHE,forecast.download=original
    after,_=source_digest(ROOT)
    if before!=after:failures.append("Source changed during live qualification; rerun on the final commit")
    report={"kind":"live_maps","status":"passed" if not failures else "failed","passed":not failures,
        "started_at":started,"finished_at":utc_now(),"elapsed_seconds":round(time.monotonic()-clock,3),
        "source_sha256":before,"source_sha256_after":after,"source_files":files,"runtime":runtime_versions(),
        "cases":records,"failures":failures,"personal_state_accessed":False,"deadline_seconds":30,
        "expected_forecast_cases":4,"completed_forecast_cases":sum("layer" in row for row in records)}
    if report["completed_forecast_cases"]!=4:
        report["passed"]=False;report["status"]="failed";report["failures"].append("Not all planned forecast cases completed")
    args.report.parent.mkdir(parents=True,exist_ok=True);atomic_json(args.report,report)
    print(json.dumps({"status":report["status"],"cases":len(records),"elapsed_seconds":report["elapsed_seconds"],"failures":report["failures"]}))
    return 0 if report["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
