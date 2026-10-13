"""One metadata schema for every instrument at NUANCE.

Vendor files describe the same physical quantities in different words and
units. Readers translate them into this schema (SI-friendly units in the key
names), and keep the untouched vendor block in ``original_metadata``::

    instrument:   vendor, model, serial
    technique:    SEM | TEM | STEM | FIB | EDS | EELS | AFM | ...
    beam:         voltage_kV, current_nA, spot
    optics:       magnification, working_distance_mm, hfw_um, camera_length_mm
    detector:     name, mode, signal
    acquisition:  datetime, dwell_us, frame_integration, line_integration, operator
    sample:       name, description, stage {x_mm, y_mm, z_mm, tilt_deg, rotation_deg}
    facility:     "NUANCE Center, Northwestern University"
"""
from __future__ import annotations

import re
from typing import Any, Optional

from .provenance import FACILITY

SECTIONS = ("instrument", "technique", "beam", "optics", "detector", "acquisition", "sample", "facility")

LENGTH_TO_NM = {"pm": 1e-3, "nm": 1.0, "Å": 0.1, "A": 0.1, "um": 1e3, "µm": 1e3, "μm": 1e3, "micron": 1e3,
                "mm": 1e6, "cm": 1e7, "m": 1e9}


def empty() -> dict:
    return {"instrument": {}, "technique": None, "beam": {}, "optics": {}, "detector": {}, "acquisition": {},
            "sample": {}, "facility": FACILITY}


def to_nm(value: float, unit: str) -> Optional[float]:
    f = LENGTH_TO_NM.get((unit or "").strip())
    return None if f is None else float(value) * f


def number(s: Any) -> Optional[float]:
    """First number in a string ('5.00 kV' -> 5.0, '10.00 K X' -> 10.0)."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", str(s))
    return float(m.group()) if m else None


def with_unit(s: str) -> tuple[Optional[float], str]:
    m = re.match(r"\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([^\s\d]*)", str(s))
    return (float(m.group(1)), m.group(2)) if m else (None, "")


def get(md: dict, dotted: str, default=None):
    cur: Any = md
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def put(md: dict, dotted: str, value) -> None:
    if value is None or value == "":
        return
    *path, last = dotted.split(".")
    cur = md
    for k in path:
        cur = cur.setdefault(k, {})
    cur[last] = value


def merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in (extra or {}).items():
        out[k] = merge(out.get(k, {}), v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def summary(md: dict) -> list[str]:
    """Short human-readable lines for the most useful fields."""
    rows = [
        ("Instrument", " ".join(str(x) for x in (get(md, "instrument.vendor"), get(md, "instrument.model")) if x)),
        ("Technique", get(md, "technique")),
        ("Voltage", f"{get(md, 'beam.voltage_kV'):g} kV" if get(md, "beam.voltage_kV") is not None else None),
        ("Beam current", f"{get(md, 'beam.current_nA'):g} nA" if get(md, "beam.current_nA") is not None else None),
        ("Magnification", f"{get(md, 'optics.magnification'):,.0f}×" if get(md, "optics.magnification") else None),
        ("Camera length", f"{get(md, 'optics.camera_length_mm'):g} mm" if get(md, "optics.camera_length_mm") else None),
        ("Working distance", f"{get(md, 'optics.working_distance_mm'):g} mm" if get(md, "optics.working_distance_mm") is not None else None),
        ("Detector", " ".join(str(x) for x in (get(md, "detector.name"), get(md, "detector.mode")) if x)),
        ("Dwell", f"{get(md, 'acquisition.dwell_us'):g} µs" if get(md, "acquisition.dwell_us") is not None else None),
        ("Acquired", get(md, "acquisition.datetime")),
        ("Operator", get(md, "acquisition.operator")),
        ("Sample", get(md, "sample.name")),
        ("Software", get(md, "acquisition.software")),
    ]
    return [f"{k}: {v}" for k, v in rows if v]


__all__ = ["empty", "get", "put", "merge", "number", "with_unit", "to_nm", "summary", "SECTIONS"]
