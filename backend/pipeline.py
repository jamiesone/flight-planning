"""Orchestration — one `query()` that runs the whole pipeline.

    takeoff (lat, lon, time) → winds + reachability disk
                             → graph-gated reachable subgraph (+ DABS join)
                             → relevance ranking
                             → Gemini answer (cited trajectories)

The static graph (airspace + docs + DABS) is built once and memorised; only the
per-query reachability traversal and the LLM call run each time.
"""
from __future__ import annotations
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import wind, graph, rag, llm, config

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path = ROOT / ".env") -> None:
    """Minimal .env loader (no dependency); does not overwrite existing vars."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


load_env()

_GRAPH = None
_DABS_DAY = None


def get_graph(which: str = "today"):
    """Static graph (built once, memoised) with the requested DABS bulletin
    layered on. Swaps the DABS layer if a different day is needed; falls back to
    today's bulletin if the requested one can't be fetched."""
    global _GRAPH, _DABS_DAY
    if _GRAPH is None:
        _GRAPH = graph.build_graph()
    if _DABS_DAY != which:
        graph.remove_dabs_layer(_GRAPH)
        try:
            graph.add_dabs_layer(_GRAPH, which)
            _DABS_DAY = which
        except Exception:
            graph.add_dabs_layer(_GRAPH, "today")
            _DABS_DAY = "today"
    return _GRAPH


def dabs_status(w: dict) -> dict:
    """Which DABS bulletin applies to the flight window, and whether it's been
    published yet. The DABS for day D is released at 16:00 local on D-1, so a
    flight on a not-yet-published day gets a provisional warning."""
    flight_date = w["time"][:10]
    now_local = (datetime.now(timezone.utc)
                 + timedelta(minutes=w.get("offset_min", 0))).replace(tzinfo=None)
    pub = (datetime.fromisoformat(flight_date) - timedelta(days=1)).replace(
        hour=16, minute=0, second=0, microsecond=0)
    published = now_local >= pub
    today = now_local.date().isoformat()
    tomorrow = (now_local.date() + timedelta(days=1)).isoformat()
    which = "tomorrow" if (flight_date == tomorrow and published) else "today"
    warning = None
    if not published:
        warning = (f"NOTAM data is PROVISIONAL: the DABS bulletin for your flight day "
                   f"({flight_date}) is published at 16:00 local the day before and is not "
                   f"yet available. Restricted/danger-area activations may change — re-check "
                   f"after 16:00, once the DABS for {flight_date} is published.")
    return {"bulletin": which, "provisional": not published,
            "warning": warning, "flight_date": flight_date}


def query(lat: float, lon: float, question: str | None = None, *,
          mode: str | None = None, name: str = "Takeoff",
          call_llm: bool = False) -> dict:
    """Run the pipeline for a takeoff point.

    `mode` ('morning'/'evening') comes from the dashboard toggle and selects the
    flight window; airspace/docs are fetched with the max-of-windows radius so
    the map is stable across the toggle. `question` (optional) is the pilot's
    flight question — it ranks the rules chunks and is answered by the LLM, which
    runs only when `call_llm` is set (i.e. the user asked for a plan)."""
    raw = wind.fetch_wind(lat, lon)
    w = wind.wind_at_takeoff(lat, lon, mode=mode)        # None -> soonest window
    w["radius_km"] = wind.max_window_radius(raw)         # operative fetch radius
    dabs = dabs_status(w)
    G = get_graph(dabs["bulletin"])
    sub = graph.reachable_subgraph(G, lon, lat, w["radius_km"], w["utc_window"])
    rag.rank_context(G, sub, w, question)
    takeoff = {"name": name, "lat": lat, "lon": lon}
    out = {"takeoff": takeoff, "wind": w, "context": sub, "dabs": dabs}
    if call_llm:
        try:
            out["llm"] = llm.generate(takeoff, w, sub, question, notice=dabs["warning"])
        except Exception as e:                       # keep the dashboard usable
            out["llm"] = {"error": str(e), "sources": llm.sources_used(sub)}
    return out


if __name__ == "__main__":
    t = config.DEMO_TAKEOFF
    r = query(t["lat"], t["lon"], name=t["name"], call_llm=True,
              question="I'd like to fly toward open farmland for an easy landing — what are my options?")
    print(f"=== {r['takeoff']['name']}  {r['wind']['time']}  "
          f"reach {r['wind']['radius_km']}km  model={r['llm']['model']} ===\n")
    print(r["llm"]["answer"])
    print("\nSOURCES:", [s["name"] for s in r["llm"]["sources"]])
