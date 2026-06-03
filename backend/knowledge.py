""" Decisions encoded here:
  * Retrieved corpus = the two English .md summaries (chunked per section).
  * The three BAZL PDFs are cited *source* documents (IDs match their official
    directive references), linked by `derived_from` only where the summary
    actually cites them.
  * Wildlife (W) is excluded upstream in airspace.load_zones.
"""
from __future__ import annotations
from . import config

SOURCES = config.DATA / "sources"

# --- live structured feeds (Dataset nodes) ---------------------------------
DATASETS = {
    "dataset:shv-fsvl": {"name": "SHV/FSVL airspace", "url": config.SHV_AIRSPACE_URL},
    "dataset:open-meteo": {"name": "Open-Meteo", "url": config.OPEN_METEO_URL},
}

# --- documents -------------------------------------------------------------
# corpus=True -> chunked & retrievable; corpus=False -> cited authority only.
# PDF IDs use the official directive reference (doc:lr-i-004, etc.).
DOC_REGISTRY = {
    "doc:classes": {
        "title": "Airspace Classes in Switzerland",
        "path": config.DOCS / "airspace_classes_switzerland.md",
        "corpus": True,
        "derived_from": ["doc:vrv-l-app139", "doc:sera-app4"],
    },
    "doc:types": {
        "title": "Airspace Types in Switzerland",
        "path": config.DOCS / "airspace_types_switzerland.md",
        "corpus": True,
        "derived_from": ["doc:lr-i-004"],
    },
    "doc:vrv-l-app139": {
        "title": "VRV-L Appendix 139 — Use of airspace classes in Switzerland",
        "path": SOURCES / "application_airspace_classes_vrv-l.pdf",
        "corpus": False,
        "url": "https://www.bazl.admin.ch/dam/fr/sd-web/hGSCX17weZW-/anwendung_der_luftraumklassen_in_derschweiz_gemaess_anhang_1_der_vrv-l.pdf",
    },
    "doc:sera-app4": {
        "title": "SERA Appendix 4 — ATS airspace classes (ICAO)",
        "path": SOURCES / "icao_classification.pdf",
        "corpus": False,
        "url": None,
    },
    "doc:lr-i-004": {
        "title": "BAZL PRD Directive LR I-004 — Prohibited / Restricted / Danger areas",
        "path": SOURCES / "prd_richtlinie_lr_i_004.pdf",
        "corpus": False,
        "url": "https://www.bazl.admin.ch/dam/fr/sd-web/9IcLLYcQo-Z6/prd-richtlinie_lr_i_004_d.pdf",
    }
}

# --- always-on chunks (cross-cutting rules, like ambient E/G) --------------
# Sections that apply to every flight regardless of the reachable airspace, so
# they're always included in retrieval. Keyed by their parsed section heading.
ALWAYS_ON_CHUNKS = [
    {"id": "ref:vfr-limits", "doc": "doc:classes",
     "section": "VFR Ceiling & Onboard Equipment",
     "label": "VFR Ceiling & Onboard Equipment"},
]


# --- airspace classes (sections of classes.md) -----------------------------
# ambient=True -> always in retrieval context (no polygon references them, but
# every balloon launches/cruises through Class G and E).
CLASS_NODES = {"C": False, "D": False, "E": True, "G": True}

# --- airspace types (SHV ASType) -> types.md section -----------------------
# Only types with a dedicated section get text via has_type; the rest reach
# rules through their class (has_class) or ambient E/G, per the data-grounded
# mapping. Section codes match the headings parsed from types.md.
TYPE_TO_SECTION = {
    "CTR": "CTR",
    "TMA": "TMA",
    "RMZ": "RMZ",
    "R": "LS-R",
    "Q": "LS-D",
}

TYPE_LABELS = {
    "CTR": "Control Zone",
    "TMA": "Terminal Manoeuvring Area",
    "CTA": "Control Area",
    "R": "Restricted Area (LS-R)",
    "Q": "Danger Area (LS-D)",
    "RMZ": "Radio Mandatory Zone",
    "FIZ": "Flight Information Zone",
    "AWY": "Airway",
    "Airfield": "Aerodrome",
    "Heliport": "Heliport",
}
