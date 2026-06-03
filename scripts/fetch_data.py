#!/usr/bin/env python
"""Fetch the live data the app needs into data/cache/ (which is gitignored).

Run once from a clean checkout:

    python scripts/fetch_data.py

This pulls the SHV/FSVL airspace GeoJSON and today's DABS bulletin (and
tomorrow's, if it has been published). The cited BAZL source PDFs live in
data/sources/ (committed). Winds are fetched on demand per query, so they are
not part of setup.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import airspace, dabs, config  # noqa: E402


def main() -> None:
    config.CACHE.mkdir(parents=True, exist_ok=True)

    # Force fresh copies (clear any stale cache first).
    for f in [config.CACHE / "airspaces_raw.geojson",
              config.CACHE / "dabs_today.pdf",
              config.CACHE / "dabs_tomorrow.pdf"]:
        f.unlink(missing_ok=True)

    print("Fetching SHV/FSVL airspace ...")
    fc = airspace.fetch_raw(cache=True)
    print(f"  -> {len(fc['features'])} airspace features "
          f"({len(airspace.load_zones())} after dropping wildlife)")

    for day in ("today", "tomorrow"):
        print(f"Fetching DABS ({day}) ...")
        try:
            ns = dabs.load_notams(day, cache=True)
            print(f"  -> {len(ns)} NOTAMs")
        except Exception as e:
            note = " (not published until 16:00 local)" if day == "tomorrow" else ""
            print(f"  -> unavailable{note}: {e}")

    print("\nDone. Winds are fetched on demand per query.")
    print("Next: copy .env.example to .env, add GEMINI_API_KEY, then")
    print("      uvicorn backend.api:app --reload")


if __name__ == "__main__":
    main()
