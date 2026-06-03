"""Relevance ranking over the graph-gated context.

The graph decides WHAT is in scope (reachable zones, their rules chunks, in-reach
NOTAMs). This layer decides what MATTERS for a balloon, so the LLM receives an
ordered, prioritised context instead of a flat dump.

Operational relevance (primary) multiplies four factors:
  proximity        nearer the takeoff/reach = higher
  altitude overlap does the zone's band overlap the flight envelope? (a balloon
                   can't enter an FL100 R-area, so it barely matters)
  applicability    what it means *for a balloon*: restriction/controlled high,
                   danger high, radio medium, other-user traffic (drones) low
  active           live during the flight window? inactive/transitable -> low

A lexical overlap with the user's question is an optional secondary tie-break.
"""
from __future__ import annotations
import re

from . import config

# kind -> (label, applicability weight) for airspace zones
ZONE_APPLICABILITY = {
    "R": ("restricted", 1.0), "Q": ("danger", 0.9),
    "CTR": ("controlled", 1.0), "TMA": ("controlled", 0.9), "CTA": ("controlled", 0.8),
    "AWY": ("controlled", 0.5), "RMZ": ("radio-mandatory", 0.6),
    "Airfield": ("aerodrome traffic", 0.3), "Heliport": ("aerodrome traffic", 0.3),
    "FIZ": ("information", 0.3),
}


def notam_applicability(text: str) -> tuple[str, float]:
    """Classify a NOTAM's relevance to a balloon from its text."""
    t = (text or "").upper()
    if any(k in t for k in ("DRONE", "UNMANNED", "BVLOS", "RPAS", "UAS")):
        return "drone / other-user traffic", 0.2
    if "D-AREA" in t or "DANGER" in t:
        return "danger", 0.9
    if "R-AREA" in t or "RESTRICTED" in t:
        return "restricted", 1.0
    if "ADVISED" in t:
        return "advisory", 0.5
    return "other", 0.5


def _amsl(bound, default):
    return bound["amsl_m"] if bound and bound.get("amsl_m") is not None else default


def _altitude_overlap(lower, upper, envelope) -> float:
    """1.0 if the band overlaps the flight envelope, else a small floor (the
    balloon can't reach it, but we don't drop it entirely)."""
    floor, ceil = envelope
    lo, up = _amsl(lower, 0.0), _amsl(upper, 1e9)
    return 1.0 if (lo <= ceil and up >= floor) else 0.15


def _proximity(distance_km: float, radius_km: float) -> float:
    if radius_km <= 0:
        return 1.0
    return max(0.1, 1.0 - distance_km / radius_km)


def _zone_active_factor(status: str) -> float:
    if "inactive" in status:
        return 0.3
    if status.startswith("HX") or "HX" in status:
        return 0.6
    return 1.0


def _lexical(question: str | None, text: str) -> float:
    """Fraction of question word-tokens present in the chunk (cheap tie-break)."""
    if not question:
        return 0.0
    q = {w for w in re.findall(r"[a-z]{3,}", question.lower())}
    if not q:
        return 0.0
    t = set(re.findall(r"[a-z]{3,}", (text or "").lower()))
    return len(q & t) / len(q)


def rank_context(G, sub: dict, wind: dict, question: str | None = None) -> dict:
    """Score and sort the graph-gated context in place; returns `sub`."""
    envelope = wind["envelope_m"]
    radius = wind["radius_km"]

    # zones
    node_score: dict[str, float] = {}
    for z in sub["in_reach"]:
        label, appl = ZONE_APPLICABILITY.get(z["kind"], ("other", 0.5))
        rel = (appl
               * _altitude_overlap(z["lower"], z["upper"], envelope)
               * _proximity(z["distance_km"], radius)
               * _zone_active_factor(z["status"]))
        z["applies"] = label
        z["relevance"] = round(rel, 3)
        for _, tgt, k in G.out_edges(z["id"], keys=True):
            if k in ("has_class", "has_type"):
                node_score[tgt] = max(node_score.get(tgt, 0.0), rel)
    sub["in_reach"].sort(key=lambda z: z["relevance"], reverse=True)

    # standalone NOTAM obstacles
    for o in sub["notam_obstacles"]:
        label, appl = notam_applicability(o["text"])
        rel = (appl
               * _altitude_overlap(o["lower"], o["upper"], envelope)
               * (1.0 if o["live"] else 0.3))
        o["applies"] = label
        o["relevance"] = round(rel, 3)
    sub["notam_obstacles"].sort(key=lambda o: o["relevance"], reverse=True)

    # chunks: ride on their triggering zones; ambient/always-on get a baseline
    for c in sub["chunks"]:
        base = node_score.get(c["node"], 0.5 if c.get("ambient") else 0.4)
        c["relevance"] = round(base + 0.2 * _lexical(question, c["text"]), 3)
    sub["chunks"].sort(key=lambda c: c["relevance"], reverse=True)
    return sub
