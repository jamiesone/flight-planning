"""Knowledge graph construction and the per-query reachability traversal.

Static graph (built once from the airspace API + the curated knowledge):

    Dataset  --provides-->  Airspace
    Dataset  --covers-->    Region(coverage)
    Document --contains-->  AirspaceClass | AirspaceType | Reference
    Document --derived_from--> Document        (FOCA source documents are summarised)
    Airspace --has_class--> AirspaceClass
    Airspace --has_type-->  AirspaceType

NOTAMs are a daily layer added later by the DABS parser:

    Document:DABS --contains--> Notam
    Airspace --activated_by--> Notam
"""
from __future__ import annotations
import re
import networkx as nx

from . import airspace, geo, knowledge, documents, dabs


def build_graph(*, cache: bool = True) -> nx.MultiDiGraph:
    G = nx.MultiDiGraph()

    # datasets
    for did, meta in knowledge.DATASETS.items():
        G.add_node(did, ntype="Dataset", **meta)

    # documents (corpus + cited PDFs)
    for did, meta in knowledge.DOC_REGISTRY.items():
        G.add_node(did, ntype="Document", title=meta["title"],
                   path=str(meta["path"]), url=meta.get("url"),
                   corpus=meta.get("corpus", False))
    for did, meta in knowledge.DOC_REGISTRY.items():
        for src in meta.get("derived_from", []):
            G.add_edge(did, src, key="derived_from", rel="derived_from")

    # coverage region
    G.add_node("region:switzerland", ntype="Region", role="coverage", name="Switzerland")
    for did in knowledge.DATASETS:
        G.add_edge(did, "region:switzerland", key="covers", rel="covers")

    # airspace classes (text from classes.md sections)
    class_sections = documents.parse_sections(knowledge.DOC_REGISTRY["doc:classes"]["path"])
    for code, ambient in knowledge.CLASS_NODES.items():
        text = class_sections.get(code)
        nid = f"class:{code}"
        G.add_node(nid, ntype="AirspaceClass", code=code, ambient=ambient, text=text)
        if text:
            G.add_edge("doc:classes", nid, key="contains", rel="contains")

    # always-on reference chunks (cross-cutting rules, like ambient E/G)
    doc_sections = {"doc:classes": class_sections}
    for ref in knowledge.ALWAYS_ON_CHUNKS:
        text = doc_sections.get(ref["doc"], {}).get(ref["section"])
        G.add_node(ref["id"], ntype="Reference", label=ref["label"],
                   text=text, always_on=True)
        if text:
            G.add_edge(ref["doc"], ref["id"], key="contains", rel="contains")

    # airspace types (text from types.md sections where mapped)
    type_sections = documents.parse_sections(knowledge.DOC_REGISTRY["doc:types"]["path"])
    for code, label in knowledge.TYPE_LABELS.items():
        section = knowledge.TYPE_TO_SECTION.get(code)
        text = type_sections.get(section) if section else None
        nid = f"type:{code}"
        G.add_node(nid, ntype="AirspaceType", code=code, label=label, text=text)
        if text:
            G.add_edge("doc:types", nid, key="contains", rel="contains")

    # airspace zones
    for z in airspace.load_zones(cache=cache):
        nid = f"zone:{z['id']}"
        G.add_node(nid, ntype="Airspace", name=z["name"], kind=z["kind"],
                   asclass=z["asclass"], lower=z["lower"], upper=z["upper"],
                   dabs=z["dabs"], hx=z["hx"], geometry=z["geometry"])
        G.add_edge("dataset:shv-fsvl", nid, key="provides", rel="provides")
        if f"type:{z['kind']}" in G:
            G.add_edge(nid, f"type:{z['kind']}", key="has_type", rel="has_type")
        if z["asclass"] and f"class:{z['asclass']}" in G:
            G.add_edge(nid, f"class:{z['asclass']}", key="has_class", rel="has_class")

    return G


def remove_dabs_layer(G: nx.MultiDiGraph) -> None:
    """Drop the current DABS layer (Notam nodes + doc:dabs + their edges) so a
    different day's bulletin can be loaded."""
    drop = [n for n, d in G.nodes(data=True)
            if d.get("ntype") == "Notam" or n == "doc:dabs"]
    G.remove_nodes_from(drop)


def _zone_codes(name: str) -> set[str]:
    """AIP codes a zone name carries, hyphens removed: 'TMA/LS-R80 T ...' -> {'TMA','LSR80'}."""
    first = name.split()[0] if name else ""
    return {re.sub(r"-", "", tok).upper() for tok in first.split("/")}


def _zone_matches_aip(zone_name: str, aip: str | None) -> bool:
    return bool(aip) and re.sub(r"-", "", aip).upper() in _zone_codes(zone_name)


def add_dabs_layer(G: nx.MultiDiGraph, which: str = "today", *,
                   cache: bool = True) -> nx.MultiDiGraph:
    """Daily layer: Document(DABS) --contains--> Notam, plus the cross-source
    Airspace --activated_by--> Notam join (named AIP-areas matched to zones)."""
    notams = dabs.load_notams(which, cache=cache)
    doc_id = "doc:dabs"
    title = f"DABS {notams[0]['date']}" if notams else "DABS"
    G.add_node(doc_id, ntype="Document", title=title, corpus=False, kind="bulletin")

    zones = [(n, d) for n, d in G.nodes(data=True) if d.get("ntype") == "Airspace"]
    for n in notams:
        nid = f"notam:{n['id']}"
        G.add_node(nid, ntype="Notam", notam_nr=n["notam_nr"], aip_area=n["aip_area"],
                   validity=n["validity"], lower=n["lower"], upper=n["upper"],
                   centre=n["centre"], radius_km=n["radius_km"], text=n["text"])
        G.add_edge(doc_id, nid, key="contains", rel="contains")
        if n["aip_area"]:
            for zid, zd in zones:
                if _zone_matches_aip(zd["name"], n["aip_area"]):
                    G.add_edge(zid, nid, key="activated_by", rel="activated_by")
    return G


def _overlaps(validity: list[dict], window: tuple[int, int] | None) -> bool:
    """Does any UTC validity window overlap the flight window [start, end] min?"""
    if window is None:
        return False
    s, e = window
    return any(w["from_min"] < e and s < w["to_min"] for w in validity)


def _zone_activations(G, zone_id, window):
    """NOTAMs that activate a zone (optionally only those live in `window`)."""
    out = []
    for _, nid, k in G.out_edges(zone_id, keys=True):
        if k != "activated_by":
            continue
        n = G.nodes[nid]
        out.append({"id": nid, "aip": n["aip_area"], "text": n["text"],
                    "validity": n["validity"],
                    "live": _overlaps(n["validity"], window)})
    return out


def _zone_status(d: dict, activations: list[dict], window) -> str:
    """Active/inactive verdict for the flight window, using the DABS join."""
    if d["dabs"]:
        live = [a for a in activations if a["live"]]
        if live:
            return "ACTIVE — " + ", ".join(a["aip"] for a in live)
        if window is not None:
            return "inactive for your window (not in today's DABS) — transitable"
        return "DABS-activated — check daily bulletin"
    if d["hx"]:
        return "HX — may activate without notice"
    return "active (permanent / standard hours)"


def reachable_subgraph(G: nx.MultiDiGraph, lon: float, lat: float,
                       radius_km: float, flight_window_utc: tuple[int, int] | None = None) -> dict:
    """Traverse the graph from the reachability disk.

    Returns in-reach zones (sorted by distance), the class/type nodes they
    reach, the always-on ambient classes, and the deduplicated retrieval chunks
    — i.e. exactly the document text the graph permits the LLM to see.
    """
    in_reach = []
    for n, d in G.nodes(data=True):
        if d.get("ntype") != "Airspace":
            continue
        if geo.geom_within_disk(d["geometry"], lon, lat, radius_km):
            acts = _zone_activations(G, n, flight_window_utc)
            in_reach.append({
                "id": n, "name": d["name"], "kind": d["kind"], "asclass": d["asclass"],
                "lower": d["lower"], "upper": d["upper"],
                "status": _zone_status(d, acts, flight_window_utc),
                "activations": acts,
                "distance_km": round(geo.min_distance_km(d["geometry"], lon, lat), 1),
                "geometry": d["geometry"],
            })
    in_reach.sort(key=lambda z: z["distance_km"])

    # standalone circle NOTAMs in reach (drones, temporary areas) — obstacles.
    # Named AIP-areas are skipped: they're already represented via their zones.
    notam_obstacles = []
    for n, d in G.nodes(data=True):
        if d.get("ntype") != "Notam" or d.get("aip_area"):
            continue
        if not d.get("centre") or not d.get("radius_km"):
            continue
        nl, nt = d["centre"]
        if geo.circle_within_disk(nl, nt, d["radius_km"], lon, lat, radius_km):
            notam_obstacles.append({
                "id": n, "aip": d["aip_area"], "text": d["text"],
                "lower": d["lower"], "upper": d["upper"],
                "radius_km": d["radius_km"], "centre": d["centre"],
                "live": _overlaps(d["validity"], flight_window_utc),
            })

    classes, types = set(), set()
    for z in in_reach:
        for _, tgt, k in G.out_edges(z["id"], keys=True):
            if k == "has_class":
                classes.add(tgt)
            elif k == "has_type":
                types.add(tgt)
    # ambient classes are always in context
    classes |= {n for n, d in G.nodes(data=True)
                if d.get("ntype") == "AirspaceClass" and d.get("ambient")}

    chunks = {}
    for n in classes:
        d = G.nodes[n]
        if d.get("text"):
            chunks[n] = {"node": n, "source": "classes.md",
                         "heading": f"Class {d['code']}", "text": d["text"],
                         "ambient": d.get("ambient", False)}
    for n in types:
        d = G.nodes[n]
        if d.get("text"):
            chunks[n] = {"node": n, "source": "types.md",
                         "heading": d["label"], "text": d["text"]}
    # always-on reference chunks (VFR ceiling, oxygen, ...)
    for n, d in G.nodes(data=True):
        if d.get("always_on") and d.get("text"):
            chunks[n] = {"node": n, "source": "classes.md",
                         "heading": d["label"], "text": d["text"], "ambient": True}

    return {"in_reach": in_reach, "notam_obstacles": notam_obstacles,
            "classes": sorted(classes), "types": sorted(types),
            "chunks": list(chunks.values())}


if __name__ == "__main__":
    from collections import Counter
    from . import config

    G = build_graph()
    nt = Counter(d["ntype"] for _, d in G.nodes(data=True))
    et = Counter(k for _, _, k in G.edges(keys=True))
    print("nodes:", dict(nt), "=", G.number_of_nodes())
    print("edges:", dict(et), "=", G.number_of_edges())

    t = config.DEMO_TAKEOFF
    sub = reachable_subgraph(G, t["lon"], t["lat"], 30.0)
    print(f"\nreachable from {t['name']} (30 km): {len(sub['in_reach'])} zones")
    print("classes reached:", [c.split(':')[1] for c in sub["classes"]])
    print("types reached:  ", [c.split(':')[1] for c in sub["types"]])
    print("retrieved chunks (graph-gated):")
    for c in sub["chunks"]:
        tag = " [ambient]" if c.get("ambient") else ""
        print(f"   - {c['source']:11} {c['heading']}{tag}")
