"""SHV/FSVL airspace ingestion.

Fetches the Swiss airspace GeoJSON, clips it to the demo region, and normalises
each feature into a flat `AirspaceZone` record with altitude bounds expressed in
metres AMSL. The output is deliberately graph-library-agnostic: it is just a
list of dicts that the graph layer turns into nodes/edges.

Altitude references in the source (`Upper`/`Lower` -> Metric.Alt.Type):
    "m QNH"  -> already AMSL
    "m AGL"  -> AMSL = value + ground elevation (PLAIN_ELEV_M in this approximate version)
    "m STD"  -> standard-pressure altitude. At the low levels relevant to a
                balloon we can assume that STD = AMSL
"""
from __future__ import annotations
import json
from typing import Iterable, Optional

import requests

from . import config


def _coords(geom: dict) -> Iterable[tuple[float, float]]:
    """Yield every (lon, lat) vertex of a GeoJSON geometry, any nesting depth."""
    def walk(c):
        if c and isinstance(c[0], (int, float)):
            yield c[0], c[1]
        else:
            for x in c:
                yield from walk(x)
    yield from walk(geom["coordinates"])


def _intersects_bbox(geom: dict, bbox: tuple) -> bool:
    if bbox is None:
        return True
    min_lon, min_lat, max_lon, max_lat = bbox
    return any(min_lon <= lon <= max_lon and min_lat <= lat <= max_lat
               for lon, lat in _coords(geom))


def normalise_alt(bound: Optional[dict], ground_m: float) -> Optional[dict]:
    """Turn an Upper/Lower bound object into {amsl_m, ref, raw} or None."""
    if not bound:
        return None
    alt = bound.get("Metric", {}).get("Alt", {})
    ref = alt.get("Type")                       # "m QNH" | "m AGL" | "m STD"
    val = alt.get("Altitude")
    if ref is None or val is None:
        return None
    if ref == "m AGL":
        amsl = val + ground_m
    else:                                       # "m QNH" or "m STD"
        amsl = float(val)
    return {"amsl_m": amsl, "ref": ref}


def fetch_raw(url: str = config.SHV_AIRSPACE_URL, *, cache: bool = True) -> dict:
    """Fetch the full airspace FeatureCollection, caching the raw response."""
    cache_path = config.CACHE / "airspaces_raw.geojson"
    if cache and cache_path.exists():
        return json.loads(cache_path.read_text())
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if cache:
        config.CACHE.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(data))
    return data


def load_zones(bbox: tuple | None = None,
               ground_m: float = config.PLAIN_ELEV_M,
               exclude_types: tuple = ("W",),
               *, cache: bool = True) -> list[dict]:
    """Return normalised AirspaceZone records.

    By default loads all of Switzerland (bbox=None); the per-query reachability
    disk does the spatial narrowing downstream. `exclude_types` drops kinds we
    deliberately ignore, i.e. wildlife (W).
    """
    fc = fetch_raw(cache=cache)
    zones: list[dict] = []
    for f in fc["features"]:
        if not _intersects_bbox(f["geometry"], bbox):
            continue
        p = f["properties"]
        if p.get("ASType") in exclude_types:
            continue
        zones.append({
            "id": p["ID"],
            "name": p.get("Name"),
            "kind": p.get("ASType"),            # AirspaceKind axis
            "asclass": p.get("ASClass"),        # AirspaceClass axis (C/D/None)
            "lower": normalise_alt(p.get("Lower"), ground_m),
            "upper": normalise_alt(p.get("Upper"), ground_m),
            "dabs": bool(p.get("DABS")),        # activated via daily bulletin
            "hx": bool(p.get("HX")),            # can activate without notice
            "frequency": p.get("Frequency"),    # radio contact — ingested, not yet surfaced
            "callsign": p.get("Callsign"),
            "geometry": f["geometry"],
        })
    return zones


def taxonomy(zones: list[dict]) -> dict:
    """Distinct kinds/classes/altitude-refs present — seeds the graph's type nodes."""
    kinds, classes, refs = set(), set(), set()
    for z in zones:
        kinds.add(z["kind"])
        if z["asclass"]:
            classes.add(z["asclass"])
        for b in (z["lower"], z["upper"]):
            if b:
                refs.add(b["ref"])
    return {"kinds": sorted(kinds),
            "classes": sorted(classes),
            "alt_refs": sorted(refs)}


if __name__ == "__main__":
    zs = load_zones()
    tax = taxonomy(zs)
    print(f"zones in region: {len(zs)}")
    print("taxonomy:", json.dumps(tax, indent=2))
    print("DABS-activated:", sum(z["dabs"] for z in zs),
          " HX:", sum(z["hx"] for z in zs))
