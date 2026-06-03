"""Assemble the ranked, graph-gated context into a prompt and ask Gemini 
to propose altitude-steered trajectories with inline source citations.

The prompt assembly (`build_user_prompt`) is testable without any API key; 
`generate` performs the network call, reading GEMINI_API_KEY (or
GOOGLE_API_KEY) and an optional GEMINI_MODEL from the environment.
"""
from __future__ import annotations
import os

SYSTEM_PROMPT = """You are a hot-air-balloon flight-planning assistant for Switzerland.

A balloon cannot steer horizontally: the pilot controls only altitude, and changes \
direction by climbing or descending into wind layers that blow different ways. Higher \
layers are usually faster.

Using ONLY the context provided (wind layers, reachable airspace, NOTAMs and the cited \
rules), propose 2-3 candidate one-hour flight plans from the takeoff point. For each plan give:
- the altitude(s) to fly and which wind layer steers the balloon where (direction + rough distance);
- the resulting drift / landing area;
- every airspace, NOTAM or altitude constraint it must respect — ATC clearance for controlled \
airspace (C/D, CTR, TMA), supplemental oxygen above 3000 m, the FL195 VFR ceiling, and any \
ACTIVE restricted/danger area. State clearly when a restricted/danger area is INACTIVE for the \
flight window (transitable).

A NOTAM tagged "drone / other-user traffic" (drone/UAS/BVLOS operations) restricts the drone \
operator, not the balloon, for a balloon it is traffic awareness at most and never a no-go. If \
you mention such a NOTAM, explain its low relevance by applicability (it does not govern balloon \
flight, and/or lies below your altitudes), not merely by it being off the flight path.

Cite specific sources inline by their bracketed name, e.g. [Class C], [Restricted Area (LS-R)], \
[DABS: LSR7], [VFR Ceiling & Onboard Equipment]. Do not invent regulations, airspace or NOTAMs \
that are not in the context. Be concise and practical, and end with a one-line recommendation."""


def _band(lower, upper) -> str:
    def m(b):
        return f"{b['amsl_m']:.0f}m" if b and b.get("amsl_m") is not None else "GND"
    return f"{m(lower)}–{m(upper)} AMSL"


def _fmt_levels(levels) -> str:
    rows = ["  altitude   speed   from→drifts-to   flags"]
    for lv in levels:
        flags = " ".join(f for f, on in
                          (("O2", lv.get("o2_required")), (">FL195", lv.get("above_vfr_ceiling"))) if on)
        rows.append(f"  {lv['level']:9} {lv['altitude_m']:5.0f}m {lv['speed_kmh']:5.1f}km/h "
                    f"from {lv['dir_from_deg']:3.0f}° → {lv['bearing_to_deg']:3.0f}°  {flags}")
    return "\n".join(rows)


def _fmt_zones(zones, limit=12) -> str:
    rows = []
    for z in zones[:limit]:
        rows.append(f"  - {z['kind']} {z['name']} (class {z['asclass'] or '—'}, {z['applies']}), "
                    f"{_band(z['lower'], z['upper'])}, {z['distance_km']}km away — {z['status']}")
    return "\n".join(rows) if rows else "  (none)"


def _fmt_notams(obstacles) -> str:
    rows = []
    for o in obstacles:
        live = "LIVE" if o["live"] else "not active for window"
        rows.append(f"  - {_band(o['lower'], o['upper'])}, {live}, {o['applies']}: {o['text']}")
    return "\n".join(rows) if rows else "  (none)"


def _fmt_chunks(chunks) -> str:
    return "\n\n".join(f"### [{c['heading']}]  (source: {c['source']})\n{c['text']}"
                       for c in chunks)


def build_user_prompt(takeoff: dict, wind: dict, sub: dict, question: str | None,
                      notice: str | None = None) -> str:
    us, ue = wind["utc_window"]
    q = question or "Propose good one-hour trajectories from this takeoff point."
    notice_block = (f"IMPORTANT NOTICE — state this clearly at the top of your answer:\n{notice}\n\n"
                    if notice else "")
    return f"""{notice_block}TAKEOFF: {takeoff['name']} ({takeoff['lat']:.4f}, {takeoff['lon']:.4f})
TIME: {wind['time']} local ({wind.get('window') or 'specified'}), flight window {us//60:02d}:{us%60:02d}–{ue//60:02d}:{ue%60:02d} UTC
FLIGHT ENVELOPE: {wind['envelope_m'][0]}–{wind['envelope_m'][1]} m AMSL   REACHABILITY RADIUS: {wind['radius_km']} km

WIND LAYERS (the only way to steer):
{_fmt_levels(wind['levels'])}

REACHABLE AIRSPACE (ranked by relevance to this flight):
{_fmt_zones(sub['in_reach'])}

NOTAM OBSTACLES IN REACH:
{_fmt_notams(sub['notam_obstacles'])}

APPLICABLE RULES (cite these by their [bracketed] name):
{_fmt_chunks(sub['chunks'])}

QUESTION: {q}
"""


def sources_used(sub: dict) -> list[dict]:
    """The grounding set, for a dashboard citation panel."""
    out = [{"name": c["heading"], "type": "rule", "source": c["source"]} for c in sub["chunks"]]
    seen = set()
    for z in sub["in_reach"]:
        for a in z.get("activations", []):
            if a["live"] and a["id"] not in seen:
                seen.add(a["id"])
                out.append({"name": f"DABS: {a['aip']}", "type": "notam", "source": "DABS"})
    out.append({"name": "Open-Meteo", "type": "data", "source": "wind"})
    out.append({"name": "SHV/FSVL", "type": "data", "source": "airspace"})
    return out


def generate(takeoff: dict, wind: dict, sub: dict, question: str | None = None,
             notice: str | None = None, *, model: str | None = None,
             max_tokens: int = 16000) -> dict:
    """Call Gemini. Returns {answer, prompt, sources, model}."""
    from google import genai
    from google.genai import types

    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("Set GEMINI_API_KEY (or GOOGLE_API_KEY) in the environment.")
    model = model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    prompt = build_user_prompt(takeoff, wind, sub, question, notice)

    client = genai.Client(api_key=key)
    resp = client.models.generate_content(
        model=model, contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT, max_output_tokens=max_tokens),
    )
    return {"answer": resp.text, "prompt": prompt,
            "sources": sources_used(sub), "model": model}
