"""Native readers for SEM / FIB-SEM images from NUANCE instruments.

Each turns the vendor's metadata into the NUScope schema and keeps the raw
block in ``original_metadata``. Instrument coverage follows the original
NUScope loaders by Nathaniel Kabat:

* Thermo Fisher / FEI (Quanta, Helios, Scios, Nova, Apreo, ...): metadata in
  TIFF tag 34682 (or 34680), or a copied ``.txt`` next to the image;
  the data bar at the bottom of the frame is removed;
* Zeiss (Gemini, Crossbeam, ...): TIFF tag 34118 (``CZ_SEM``);
* Hitachi (S-4800, SU8030, S-3400): image + ``.txt`` with ``[SemImageFile]``;
* JEOL (JSM-7900F, IT series): image + ``.txt`` with ``$CM_*`` / ``$SM_*``.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import numpy as np
import tifffile

from .. import metadata as md

FEI_TAGS = (34682, 34680)
ZEISS_TAG = 34118


# ------------------------------------------------------------------ helpers
def parse_ini(text: str) -> dict:
    """'[Section]\\nKey=Value' blocks -> {section: {key: value}} (values stay strings)."""
    out: dict = {}
    sec = "root"
    for raw in text.replace("\r", "").split("\n"):
        line = raw.strip().strip("\x00")
        if not line:
            continue
        m = re.match(r"^\[(.+)\]$", line)
        if m:
            sec = m.group(1)
            out.setdefault(sec, {})
        elif "=" in line:
            k, v = line.split("=", 1)
            out.setdefault(sec, {})[k.strip()] = v.strip()
    return out


def sidecar(path: Path) -> Optional[Path]:
    for cand in (path.with_suffix(".txt"), path.with_suffix(".TXT"),
                 path.with_name(path.stem + "-COPIED.TXT"), path.with_name(path.stem + "-COPIED.txt")):
        if cand.exists():
            return cand
    return None


def _tag(tif: tifffile.TiffFile, code: int) -> Optional[str]:
    """Raw text of a private tag (tifffile pre-parses FEI/Zeiss tags; we read the bytes
    ourselves so every file version parses the same way)."""
    t = tif.pages[0].tags.get(code)
    if t is None:
        return None
    fh = tif.filehandle
    pos = fh.tell()
    try:
        fh.seek(t.valueoffset)
        raw = fh.read(t.valuebytecount)
    finally:
        fh.seek(pos)
    return raw.decode("latin-1", "replace").replace("\x00", "\n")


def _f(d: dict, key: str) -> Optional[float]:
    try:
        return float(d[key])
    except (KeyError, TypeError, ValueError):
        return None


def _image(path: Path) -> np.ndarray:
    a = tifffile.imread(path)
    if a.ndim == 3 and a.shape[-1] in (3, 4) and np.allclose(a[..., 0], a[..., 1]):
        a = a[..., 0]   # grey image saved as RGB
    return a


# ------------------------------------------------------------------ Thermo Fisher / FEI
def thermo_from_ini(sec: dict) -> dict:
    m = md.empty()
    sysd, beam, eb, ib, scan, stage, det, user = (sec.get(k, {}) for k in
                                                  ("System", "Beam", "EBeam", "IBeam", "Scan", "Stage", "Detectors", "User"))
    ion = beam.get("Beam", "").lower().startswith("ibeam")
    b = ib if ion else eb
    md.put(m, "instrument.vendor", "Thermo Fisher Scientific")
    md.put(m, "instrument.model", sysd.get("SystemType") or sysd.get("Type"))
    md.put(m, "instrument.serial", sysd.get("Dnumber"))
    m["technique"] = "FIB" if ion else "SEM"
    hv = _f(b, "HV") or _f(beam, "HV")
    md.put(m, "beam.voltage_kV", hv / 1e3 if hv else None)
    cur = _f(b, "BeamCurrent")
    md.put(m, "beam.current_nA", cur * 1e9 if cur else None)
    md.put(m, "beam.spot", _f(beam, "Spot") or _f(b, "Spot"))
    wd = _f(b, "WD") or _f(stage, "WorkingDistance")
    md.put(m, "optics.working_distance_mm", round(wd * 1e3, 4) if wd else None)
    hfw = _f(b, "HFW") or _f(scan, "HorFieldsize")
    md.put(m, "optics.hfw_um", round(hfw * 1e6, 4) if hfw else None)
    dw = _f(sysd, "DisplayWidth")
    if hfw and dw:
        md.put(m, "optics.magnification", round(dw / hfw))
    md.put(m, "detector.name", det.get("Name"))
    md.put(m, "detector.mode", det.get("Mode"))
    dwell = _f(scan, "Dwelltime")
    md.put(m, "acquisition.dwell_us", round(dwell * 1e6, 4) if dwell else None)
    md.put(m, "acquisition.line_integration", _f(scan, "LineIntegration"))
    md.put(m, "acquisition.frame_integration", _f(scan, "FrameIntegration"))
    if user.get("Date"):
        md.put(m, "acquisition.datetime", f"{user.get('Date')} {user.get('Time', '')}".strip())
    md.put(m, "acquisition.operator", user.get("User"))
    for k, key, f in (("x_mm", "StageX", 1e3), ("y_mm", "StageY", 1e3), ("z_mm", "StageZ", 1e3),
                      ("tilt_deg", "StageT", 180 / np.pi), ("rotation_deg", "StageR", 180 / np.pi)):
        v = _f(stage, key)
        if v is not None:
            md.put(m, f"sample.stage.{k}", round(v * f, 4))
    return m


def read_thermo(path: Path, text: str, crop_databar: bool = True):
    sec = parse_ini(text)
    img = _image(path)
    scan, image = sec.get("Scan", {}), sec.get("Image", {})
    ry = _f(image, "ResolutionY") or _f(scan, "ResolutionY")
    if crop_databar and ry and img.shape[0] > ry:
        img = img[: int(ry)]
    pw, ph = _f(scan, "PixelWidth"), _f(scan, "PixelHeight")
    return img, thermo_from_ini(sec), sec, ((ph or pw) * 1e9 if (ph or pw) else None, pw * 1e9 if pw else None)


# ------------------------------------------------------------------ Zeiss
def parse_zeiss(text: str) -> dict:
    out = {}
    for line in text.replace("\r", "").split("\n"):
        if " = " in line:
            k, v = line.split(" = ", 1)
            out[k.strip().strip("\x00")] = v.strip()
    return out


def _zeiss_mag(s: str) -> Optional[float]:
    v, unit = md.with_unit(s.replace(" ", ""))
    if v is None:
        return None
    return v * 1e3 if unit.upper().startswith("K") else v


def read_zeiss(path: Path, text: str):
    z = parse_zeiss(text)
    m = md.empty()
    md.put(m, "instrument.vendor", "Carl Zeiss")
    md.put(m, "instrument.model", z.get("SEM") or z.get("Column Type"))
    md.put(m, "instrument.serial", z.get("Serial No."))
    m["technique"] = "SEM"
    if "EHT" in z or "EHT Target" in z:
        v, unit = md.with_unit(z.get("EHT") or z["EHT Target"])
        md.put(m, "beam.voltage_kV", v / 1e3 if unit == "V" else v)
    if "I Probe" in z:
        v, unit = md.with_unit(z["I Probe"])
        md.put(m, "beam.current_nA", {"pA": 1e-3, "nA": 1.0, "µA": 1e3, "uA": 1e3}.get(unit, 1.0) * v if v else None)
    if "WD" in z:
        v, unit = md.with_unit(z["WD"])
        md.put(m, "optics.working_distance_mm", md.to_nm(v, unit) / 1e6 if v is not None and md.to_nm(v, unit) else None)
    if "Mag" in z:
        md.put(m, "optics.magnification", _zeiss_mag(z["Mag"]))
    md.put(m, "detector.name", z.get("Signal A"))
    md.put(m, "acquisition.datetime", " ".join(x for x in (z.get("Date"), z.get("Time")) if x) or None)
    md.put(m, "acquisition.operator", z.get("User Name"))
    ps = None
    if "Pixel Size" in z:
        v, unit = md.with_unit(z["Pixel Size"])
        ps = md.to_nm(v, unit) if v is not None else None
    return _image(path), m, z, (ps, ps)


# ------------------------------------------------------------------ burned-in data bars
def detect_databar(img: np.ndarray, max_frac: float = 0.2) -> int:
    """Number of rows at the bottom occupied by an info bar (black band with text),
    0 if none. A bar row is mostly black; a thin white separator line counts too."""
    a = img if img.ndim == 2 else img[..., 0]
    h = a.shape[0]
    lo, hi = np.percentile(a, (0.5, 99.5)) if a.size else (0, 255)
    dark = (a <= lo + 0.03 * (hi - lo)).mean(1)
    bright = (a >= hi - 0.03 * (hi - lo)).mean(1)
    n = 0
    for r in range(h - 1, int(h * (1 - max_frac)) - 1, -1):
        if dark[r] > 0.55 or bright[r] > 0.9:
            n += 1
        else:
            break
    return n if int(0.02 * h) <= n <= int(max_frac * h) else 0


# ------------------------------------------------------------------ Hitachi
def read_hitachi(path: Path, side: Path, crop_databar: bool = True):
    text = side.read_text(errors="replace")
    sec = parse_ini(text)
    h = sec.get("SemImageFile") or next(iter(sec.values()), {})
    m = md.empty()
    md.put(m, "instrument.vendor", "Hitachi High-Tech")
    md.put(m, "instrument.model", h.get("InstructName"))
    md.put(m, "instrument.serial", h.get("SerialNumber"))
    m["technique"] = "SEM"
    v = md.number(h.get("AcceleratingVoltage"))
    md.put(m, "beam.voltage_kV", v / 1e3 if v and v > 100 else v)
    ec = md.number(h.get("EmissionCurrent"))
    md.put(m, "beam.emission_current_uA", ec / 1e3 if ec else None)
    wd = md.number(h.get("WorkingDistance"))
    md.put(m, "optics.working_distance_mm", wd / 1e3 if wd and wd > 100 else wd)
    md.put(m, "optics.magnification", md.number(h.get("Magnification")))
    md.put(m, "detector.name", h.get("SignalName"))
    md.put(m, "acquisition.datetime", " ".join(x for x in (h.get("Date"), h.get("Time")) if x) or None)
    for k, key, f in (("x_mm", "StagePositionX", 1e-6), ("y_mm", "StagePositionY", 1e-6), ("z_mm", "StagePositionZ", 1e-6),
                      ("rotation_deg", "StagePositionR", 1.0), ("tilt_deg", "StagePositionT", 1.0)):
        v = md.number(h.get(key))
        if v is not None:
            md.put(m, f"sample.stage.{k}", round(v * f, 4))
    md.put(m, "sample.name", h.get("SampleName") or None)
    ps = md.number(h.get("PixelSize"))
    img = _image(path)
    if crop_databar and str(h.get("DataDisplayCombine", "0")).strip() == "1":
        n = detect_databar(img)
        if n:
            img = img[: img.shape[0] - n]
            md.put(m, "acquisition.databar_rows_removed", n)
    return img, m, sec, (ps, ps)


# ------------------------------------------------------------------ JEOL
def parse_jeol(text: str) -> dict:
    out = {}
    for line in text.replace("\r", "").split("\n"):
        line = line.strip()
        if not line.startswith("$"):
            continue
        parts = line.lstrip("$").split(None, 1)
        out[parts[0]] = parts[1].strip() if len(parts) > 1 else ""
    return out


def read_jeol(path: Path, side: Path):
    j = parse_jeol(side.read_text(errors="replace"))
    m = md.empty()
    md.put(m, "instrument.vendor", "JEOL")
    md.put(m, "instrument.model", j.get("CM_INSTRUMENT"))
    m["technique"] = "SEM"
    md.put(m, "beam.voltage_kV", md.number(j.get("CM_ACCEL_VOLT")))
    md.put(m, "optics.magnification", md.number(j.get("CM_MAG")))
    md.put(m, "optics.working_distance_mm", md.number(j.get("SM_WD") or j.get("CM_WD")))
    md.put(m, "detector.name", j.get("CM_SIGNAL"))
    md.put(m, "acquisition.datetime", " ".join(x for x in (j.get("CM_DATE"), j.get("CM_TIME")) if x) or None)
    md.put(m, "sample.name", j.get("CM_TITLE"))
    ps = None
    bar, marker = md.number(j.get("SM_MICRON_BAR")), j.get("SM_MICRON_MARKER")
    if bar and marker:
        v, unit = md.with_unit(marker)
        nm = md.to_nm(v, unit) if v is not None else None
        ps = nm / bar if nm else None
    return _image(path), m, j, (ps, ps)


# ------------------------------------------------------------------ dispatch
def read_vendor_tiff(path: Path, crop_databar: bool = True):
    """Return (array, metadata, original_metadata, (py_nm, px_nm), vendor) or None."""
    with tifffile.TiffFile(path) as tif:
        fei = next((t for t in (_tag(tif, c) for c in FEI_TAGS) if t), None)
        zeiss = _tag(tif, ZEISS_TAG)
    if fei and "[" in fei:
        img, m, raw, ps = read_thermo(path, fei, crop_databar)
        return img, m, raw, ps, "thermo"
    if zeiss and isinstance(zeiss, str):
        img, m, raw, ps = read_zeiss(path, zeiss)
        return img, m, raw, ps, "zeiss"
    side = sidecar(path)
    if side:
        head = side.read_text(errors="replace")[:4000]
        if "[SemImageFile]" in head or "InstructName" in head:
            return (*read_hitachi(path, side, crop_databar), "hitachi")
        if "$CM_" in head or "$SM_" in head:
            return (*read_jeol(path, side), "jeol")
        if "[User]" in head or "[Beam]" in head or "[Scan]" in head:
            img, m, raw, ps = read_thermo(path, head + side.read_text(errors="replace")[4000:], crop_databar)
            return img, m, raw, ps, "thermo"
    return None


__all__ = ["read_vendor_tiff", "parse_ini", "parse_zeiss", "parse_jeol", "thermo_from_ini", "sidecar"]
