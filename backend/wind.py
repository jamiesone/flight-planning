"""Wind layer — Open-Meteo multi-level forecast at the takeoff point.

We fetch once at the takeoff location/time and treat that profile as valid for 
the whole 1-hour flight. We read winds at one surface level (120 m AGL) 
and five pressure levels (925/850/800/700/600 hPa), the pressure levels 
placed in altitude using their geopotential height (m AMSL).

Balloons fly during calm-wind windows, just after sunrise or just before sunset,
so only two take-off options are proposed: morning and evening.

Two products: the wind *field* (levels with altitude/speed/direction/drift
bearing — the layers the balloon can sit in to steer) and the reachability
radius = max windspeed over levels x 1 h (the conservative spatial gate).
Conventions: wind_direction is meteorological (degrees FROM); the balloon
drifts TOWARD direction+180. Speeds are km/h.
"""
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone

import requests

from . import config

PRESSURE_LEVELS = (925, 850, 800, 700, 600)
SURFACE_LEVELS = (120,)               # metres AGL (10 m dropped — balloons never fly that low)
HIGH_PRESSURE = (700, 600)            # time-capped: balloon won't park this high

_HOURLY = (
    [f"wind_speed_{h}m" for h in SURFACE_LEVELS]
    + [f"wind_direction_{h}m" for h in SURFACE_LEVELS]
    + [f"wind_speed_{p}hPa" for p in PRESSURE_LEVELS]
    + [f"wind_direction_{p}hPa" for p in PRESSURE_LEVELS]
    + [f"geopotential_height_{p}hPa" for p in PRESSURE_LEVELS]
)


def _cache_path(lat: float, lon: float):
    return config.CACHE / f"wind_{lat:.3f}_{lon:.3f}.json"


def fetch_wind(lat: float, lon: float, *, cache: bool = True,
               refresh: bool = False) -> dict:
    """Fetch (and cache) the Open-Meteo forecast for a point (2 days)."""
    path = _cache_path(lat, lon)
    if cache and not refresh and path.exists():
        return json.loads(path.read_text())
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": ",".join(_HOURLY),
        "daily": "sunrise,sunset",
        "wind_speed_unit": "kmh",
        "timezone": "auto",
        "forecast_days": 2,
    }
    resp = requests.get(config.OPEN_METEO_URL, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if cache:
        config.CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
    return data


# --- takeoff-time selection ------------------------------------------------

def _now_local(raw: dict) -> datetime:
    """Wall-clock time in the forecast's timezone, as a naive datetime."""
    off = raw.get("utc_offset_seconds", 0)
    return (datetime.now(timezone.utc) + timedelta(seconds=off)).replace(tzinfo=None)


def _iso_hour(t: datetime) -> str:
    """Round to the nearest hour, formatted to match Open-Meteo hourly stamps."""
    t = t.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1 if t.minute >= 30 else 0)
    return t.strftime("%Y-%m-%dT%H:00")


def choose_window(raw: dict, mode: str | None = None,
                  now: datetime | None = None) -> tuple[str, str]:
    """Pick the next calm-wind window not yet passed.

    Returns (mode, iso_hour). With `mode` set ('morning'/'evening') only that
    kind is considered; otherwise the soonest of either. Rolls into the second
    forecast day if today's windows have gone."""
    daily = raw["daily"]
    local_now = now or _now_local(raw)
    last = None
    for i in range(len(daily["time"])):
        sr = datetime.fromisoformat(daily["sunrise"][i])
        ss = datetime.fromisoformat(daily["sunset"][i])
        for m, t in (("morning", sr + timedelta(minutes=30)),
                     ("evening", ss - timedelta(hours=2))):
            if mode and m != mode:
                continue
            last = (m, _iso_hour(t))
            if local_now <= t:
                return last
    return last  # all candidate windows passed within the 2-day horizon


def pick_hour(raw: dict, at_time: str | None = None) -> int:
    """Index into the hourly arrays for `at_time` (full ISO, or 'HH:00')."""
    times = raw["hourly"]["time"]
    if at_time is None:
        at_time = choose_window(raw)[1]
    for i, t in enumerate(times):
        if t == at_time or t[11:16] == at_time:
            return i
    return 0


# --- wind field ------------------------------------------------------------

def wind_levels(raw: dict, ground_m: float = config.PLAIN_ELEV_M,
                at_time: str | None = None) -> list[dict]:
    """Altitude-sorted wind levels for the chosen hour."""
    h = raw["hourly"]
    i = pick_hour(raw, at_time)
    levels = []
    for m in SURFACE_LEVELS:
        levels.append({
            "level": f"{m}m AGL", "altitude_m": ground_m + m, "agl": True,
            "capped": False,
            "speed_kmh": h[f"wind_speed_{m}m"][i],
            "dir_from_deg": h[f"wind_direction_{m}m"][i],
        })
    for p in PRESSURE_LEVELS:
        levels.append({
            "level": f"{p} hPa", "altitude_m": h[f"geopotential_height_{p}hPa"][i],
            "agl": False, "capped": p in HIGH_PRESSURE,
            "speed_kmh": h[f"wind_speed_{p}hPa"][i],
            "dir_from_deg": h[f"wind_direction_{p}hPa"][i],
        })
    for lv in levels:
        lv["bearing_to_deg"] = (lv["dir_from_deg"] + 180) % 360
        lv["o2_required"] = lv["altitude_m"] > config.OXYGEN_ALT_M
        lv["above_vfr_ceiling"] = lv["altitude_m"] > config.VFR_CEILING_M
    levels.sort(key=lambda lv: lv["altitude_m"])
    return levels


def reachability_radius_km(levels: list[dict],
                           duration_min: int = config.FLIGHT_DURATION_MIN) -> float:
    """Time-budgeted reach (km).

    Low/mid levels can be flown the whole hour; high (capped) levels at most
    HIGH_TIME_FRAC of it. The farthest single-direction drift is therefore the
    larger of: the full hour at the fastest low/mid level, or the capped share
    at the fastest high level plus the remainder at the fastest low/mid level.
    """
    dur_h = duration_min / 60.0
    rest = [lv["speed_kmh"] for lv in levels if not lv.get("capped")]
    high = [lv["speed_kmh"] for lv in levels if lv.get("capped")]
    v_rest = max(rest) if rest else 0.0
    v_high = max(high) if high else 0.0
    f = config.HIGH_TIME_FRAC
    return max(v_rest * dur_h, v_high * f * dur_h + v_rest * (1 - f) * dur_h)


def max_window_radius(raw: dict, ground_m: float = config.PLAIN_ELEV_M) -> float:
    """Largest reachability radius across the next morning AND evening windows.

    Used to fetch airspace/documents before the takeoff time is known, so the
    displayed context covers whichever window the user ends up asking about."""
    rads = []
    for m in ("morning", "evening"):
        try:
            _, t = choose_window(raw, mode=m)
            rads.append(reachability_radius_km(wind_levels(raw, ground_m, t)))
        except Exception:
            pass
    return round(max(rads), 1) if rads else 0.0


def wind_at_takeoff(lat: float, lon: float, ground_m: float = config.PLAIN_ELEV_M,
                    at_time: str | None = None, mode: str | None = None,
                    *, cache: bool = True) -> dict:
    """Bundle: chosen time + window + levels + reachability radius."""
    raw = fetch_wind(lat, lon, cache=cache)
    window = None
    if at_time is None:
        window, at_time = choose_window(raw, mode=mode)
    i = pick_hour(raw, at_time)
    levels = wind_levels(raw, ground_m, at_time)
    off_min = raw.get("utc_offset_seconds", 0) // 60
    lt = raw["hourly"]["time"][i]
    local_min = int(lt[11:13]) * 60 + int(lt[14:16])
    utc_start = (local_min - off_min) % 1440
    utc_end = (utc_start + config.FLIGHT_DURATION_MIN) % 1440
    return {
        "time": lt,
        "window": window,
        "levels": levels,
        "radius_km": round(reachability_radius_km(levels), 1),
        "envelope_m": (round(ground_m), round(max(lv["altitude_m"] for lv in levels))),
        "utc_window": (utc_start, utc_end),
        "offset_min": off_min,
    }


if __name__ == "__main__":
    t = config.DEMO_TAKEOFF
    w = wind_at_takeoff(t["lat"], t["lon"])
    print(f"wind at {t['name']}  {w['time']} ({w['window']})   reach = {w['radius_km']} km")
    print(f"{'level':10} {'alt(m)':>7} {'spd(km/h)':>9} {'from':>5} {'->to':>5}")
    for lv in w["levels"]:
        print(f"{lv['level']:10} {lv['altitude_m']:7.0f} {lv['speed_kmh']:9.1f} "
              f"{lv['dir_from_deg']:5.0f} {lv['bearing_to_deg']:5.0f}")
