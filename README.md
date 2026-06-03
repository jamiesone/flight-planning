# Balloon Flight Planner

A demo hot-air-balloon flight planning tool, for use in the Gros-de-Vaud region. You pick a takeoff point and a window; the system fetches live winds, and works out where the balloon can reach (a balloon only controls altitude, it steers by choosing wind layers), checks the reachable Swiss airspace and the daily NOTAM bulletin, and asks an LLM to propose altitude-steered flight options.

## Setup

Requires Python 3.10+ and a Gemini API key.

```bash
# 1. virtualenv
python3 -m venv .venv
. .venv/bin/activate

# 2. dependencies
#    NOTE: some Ubuntu images ship a pip (24.0) that cannot reliably download
#    from PyPI and fails with "JSONDecodeError: Unterminated string". If that
#    happens, upgrade pip to 26.0 first.
pip install -r requirements.txt

# 3. API key
cp .env.example .env
#    then edit .env and set GEMINI_API_KEY=...   (GEMINI_MODEL defaults to gemini-2.5-flash)

# 4. fetch live data (airspace + DABS) into data/cache/
python scripts/fetch_data.py

# 5. run
uvicorn backend.api:app --reload
#    open http://127.0.0.1:8000
```

## Using the dashboard

1. Click the map somewhere in the Gros-de-Vaud region to set a takeoff point. (It also works elsewhere in Switzerland, but takes demo parameters which are not necessarily applicable in other regions.)
2. Choose whether you'd like a Morning or Evening flight, the planning is only available for the next morning/evening as DABS are not published much in advance.
3. Optionally, type any additional information relevant to the flight you're planning, e.g. whether or not you have a transponder.
4. Click on Plan flight and the LLM proposes some options for an ~1h flight. Thhe list below shows all potentially reachable airspaces/NOTAMs (click to locate on the map), a caution banner appears if the relevant DABS isn't published yet.

## Data sources

| Source | Used for | Auth | In repo? |
|---|---|---|---|
| [SHV/FSVL airspace](https://airspace.shv-fsvl.ch/doc/v2/geojson) | airspace polygons, altitude bands, DABS/HX flags | none | fetched by script |
| [Open-Meteo](https://open-meteo.com/en/docs) | multi-level winds + sunrise/sunset | none | fetched per query |
| [skybriefing DABS](https://www.skybriefing.com/o/dabs?today) | daily NOTAM bulletin | none | fetched by script |
| [swisstopo WMTS](https://www.geo.admin.ch) | basemap tiles | none | live tiles |
| BAZL VRV-L / SERA / PRD PDFs | cited airspace-rule authorities | none | `data/sources/` |
| `data/docs/*.md` | the retrieved rule corpus (classes, types) | — | committed |
