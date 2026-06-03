"""Markdown corpus parsing.

Splits a `.md` document into one section per `## ` heading and derives a stable
section code that the knowledge mapping keys off:
    "## Class D"               -> "D"
    "## CTR — Control Zone"     -> "CTR"
    "## LS-R — Restricted Area" -> "LS-R"
    "## Overview"              -> "Overview"
Each section's text (heading + body) becomes the retrievable chunk carried on
the corresponding AirspaceClass / AirspaceType node.
"""
from __future__ import annotations
from pathlib import Path


def _code(heading: str) -> str:
    if heading.startswith("Class "):
        return heading.split()[1]
    for dash in ("—", " - ", "–"):
        if dash in heading:
            return heading.split(dash)[0].strip()
    return heading.strip()


def parse_sections(path: str | Path) -> dict[str, str]:
    """Return {section_code: section_text} for a `## `-delimited markdown file."""
    sections: dict[str, str] = {}
    cur: str | None = None
    buf: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if cur is not None:
                sections[cur] = "\n".join(buf).strip()
            cur = _code(line[3:].strip())
            buf = [line]
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        sections[cur] = "\n".join(buf).strip()
    return sections
