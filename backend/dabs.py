"""DABS (Daily Airspace Bulletin Switzerland) parsing — the daily NOTAM layer.

Skyguide publishes the DABS as a PDF: page 0 is the chart, pages 1+ are a
structured 8-column table of activations. pdfplumber recovers the columns
cleanly (multi-line cells separated by '\\n'), so we parse per-row rather than
per-line. Each row yields a Notam:

    AIP-Area / NOTAM-Nr | Validity UTC | Lower | Upper | Centre | Radius | Text

Every item carries a centre point + covering radius, so each NOTAM is a circle.
Named items also carry an AIP-Area code (LSR7, LSD12, ...) which is the join key
back to the SHV airspace polygons; ad-hoc items (drones, temporary areas) have
only a NOTAM-Nr and stand alone.

Limits normalise to metres AMSL (GND->0, 'Xm / Yft'->X m, 'FLxxx'->xxx*100 ft);
validity windows are kept as UTC minutes-of-day for overlap tests against the
flight window.
"""
from __future__ import annotations
import json
import re

import pdfplumber
import requests

from . import config

FT_M = 0.3048
DABS_URLS = {"today": config.DABS_TODAY_URL, "tomorrow": config.DABS_TOMORROW_URL}


def fetch_dabs(which: str = "today", *, cache: bool = True, refresh: bool = False):
    """Download (and cache) a DABS PDF. Returns the cached path."""
    path = config.CACHE / f"dabs_{which}.pdf"
    if cache and not refresh and path.exists():
        return path
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
    resp = requests.get(DABS_URLS[which], headers=headers, timeout=60)
    resp.raise_for_status()
    config.CACHE.mkdir(parents=True, exist_ok=True)
    path.write_bytes(resp.content)
    return path


# --- field parsers ---------------------------------------------------------

def _dms(token: str) -> float:
    """'470140N' or '0085126E' -> signed decimal degrees."""
    hemi, digits = token[-1], token[:-1]
    if hemi in "NS":
        d, m, s = int(digits[0:2]), int(digits[2:4]), int(digits[4:6])
    else:
        d, m, s = int(digits[0:3]), int(digits[3:5]), int(digits[5:7])
    val = d + m / 60 + s / 3600
    return -val if hemi in "SW" else val


def parse_centre(cell: str) -> tuple[float, float] | None:
    """'470140N 0085126E' -> (lon, lat)."""
    m = re.search(r"(\d{6}[NS])\s+(\d{7}[EW])", cell or "")
    if not m:
        return None
    return _dms(m.group(2)), _dms(m.group(1))


def parse_limit(cell: str) -> dict:
    """Normalise a limit cell to {amsl_m, raw}."""
    s = (cell or "").strip()
    u = s.upper()
    if u in ("GND", "SFC", ""):
        return {"amsl_m": 0.0, "raw": s or "GND"}
    if u.startswith("FL"):
        return {"amsl_m": int(re.sub(r"\D", "", u)) * 100 * FT_M, "raw": s}
    m = re.search(r"([\d.]+)\s*m", s)
    if m:
        return {"amsl_m": float(m.group(1)), "raw": s}
    f = re.search(r"([\d.]+)\s*ft", s)
    if f:
        return {"amsl_m": float(f.group(1)) * FT_M, "raw": s}
    return {"amsl_m": None, "raw": s}


def parse_validity(cell: str) -> list[dict]:
    """'0600 - 1000\\n1100 - 2100' -> [{from_utc, to_utc, from_min, to_min}, ...]."""
    out = []
    for m in re.finditer(r"(\d{4})\s*-\s*(\d{4})", cell or ""):
        a, b = m.group(1), m.group(2)
        out.append({"from_utc": a, "to_utc": b,
                    "from_min": int(a[:2]) * 60 + int(a[2:]),
                    "to_min": int(b[:2]) * 60 + int(b[2:])})
    return out


def parse_radius_km(cell: str) -> float | None:
    m = re.search(r"([\d.]+)\s*KM", (cell or "").upper())
    return float(m.group(1)) if m else None


def _designators(cell: str) -> tuple[str | None, str | None]:
    """col1 -> (notam_nr, aip_area). Either may be None."""
    notam_nr = aip = None
    for part in (cell or "").split("\n"):
        p = part.strip().lstrip("!").strip()
        if re.fullmatch(r"[A-Z]\d+/\d+", p):
            notam_nr = notam_nr or p
        elif re.match(r"LS[A-Z]?-?[A-Z]?\d", p) or p:
            aip = aip or p
    return notam_nr, aip


def parse_dabs(path) -> list[dict]:
    """Parse a DABS PDF into Notam records."""
    notams: list[dict] = []
    with pdfplumber.open(path) as pdf:
        date = None
        for page in pdf.pages:
            txt = page.extract_text() or ""
            m = re.search(r"DABS Date:\s*([\d A-Z]+)", txt)
            if m:
                date = m.group(1).strip()
            for table in page.extract_tables():
                for row in table:
                    if len(row) < 8 or not row[5]:
                        continue                      # section/header rows
                    centre = parse_centre(row[5])
                    if centre is None:
                        continue
                    notam_nr, aip = _designators(row[1])
                    notams.append({
                        "id": notam_nr or aip or f"dabs-{len(notams)}",
                        "notam_nr": notam_nr,
                        "aip_area": aip,
                        "validity": parse_validity(row[2]),
                        "lower": parse_limit(row[3]),
                        "upper": parse_limit(row[4]),
                        "centre": centre,                 # (lon, lat)
                        "radius_km": parse_radius_km(row[6]),
                        "text": " ".join((row[7] or "").split()),
                        "date": date,
                    })
    return notams


def load_notams(which: str = "today", *, cache: bool = True) -> list[dict]:
    return parse_dabs(fetch_dabs(which, cache=cache))


if __name__ == "__main__":
    ns = load_notams("today")
    print(f"parsed {len(ns)} NOTAMs from DABS\n")
    for n in ns:
        c = n["centre"]
        wins = " ".join(f"{v['from_utc']}-{v['to_utc']}" for v in n["validity"])
        print(f"  {n['id']:10} aip={str(n['aip_area']):10} {wins:12} "
              f"{n['lower']['raw']:>6}->{n['upper']['raw']:<14} "
              f"r={n['radius_km']}km @({c[0]:.3f},{c[1]:.3f})")
        print(f"             {n['text'][:90]}")
