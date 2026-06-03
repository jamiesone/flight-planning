"""Central configuration: endpoints, the demo region, and physical constants.

Everything spatial is WGS84 / EPSG:4326 (lon, lat) to match Leaflet and the
SHV/FSVL GeoJSON. Altitudes are normalised to metres above mean sea level
(AMSL) throughout the pipeline; see `airspace.normalise_alt`.
"""
from __future__ import annotations
from pathlib import Path

# --- paths -----------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = DATA / "cache"
DOCS = DATA / "docs"

# --- data sources ----------------------------------------------------------
SHV_AIRSPACE_URL = "https://airspace.shv-fsvl.ch/api/v2/geojson/airspaces"
DABS_TODAY_URL = "https://www.skybriefing.com/o/dabs?today"
DABS_TOMORROW_URL = "https://www.skybriefing.com/o/dabs?tomorrow"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# --- demo takeoff: a representative point in the gros de Vaud plain ---------
# All Swiss airspace is ingested (airspace.load_zones); the per-query
# reachability disk does the spatial narrowing, so there is no fixed region bbox.
DEMO_TAKEOFF = {"lat": 46.66, "lon": 6.65, "name": "Gros de Vaud (plain)"}

# --- physical assumptions for the demo -------------------------------------
# The gros de Vaud is treated as a flat plain at this elevation. Used to turn
# AGL airspace bounds into AMSL, and as the flight's start/end altitude.
PLAIN_ELEV_M = 600.0
FLIGHT_DURATION_MIN = 60      # demo flight length

# Winds at 700/600 hPa (~3000/4200 m) are fetched so the LLM can reason about
# high trajectories, but a balloon will not stay a long time at these altitudes
# typically, so to keep the reachability radius bounded we assume max. 1/3 of the flight
HIGH_TIME_FRAC = 1.0 / 3.0

# Altitude thresholds used to flag wind levels / proposed trajectories.
VFR_CEILING_M = 5950.0        # FL195 — hard VFR ceiling
OXYGEN_ALT_M = 3000.0         # supplemental oxygen required above (AMSL)
