"""Delegate to RosettaSciIO for the long tail of electron-microscopy formats and
translate its metadata tree into the NUScope schema."""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Optional

import numpy as np

from .. import metadata as md
from ..dataset import Axis, Dataset

# HDF5-based and other ambiguous extensions are tried in this order.
PREFERRED = {"h5": ["Delmic", "Arina", "Tofwerk", "USID"], "hdf5": ["USID", "Delmic"], "mrc": ["MRC", "MRCZ"],
             "xml": ["EMPAD", "JobinYvon"], "csv": ["Protochips", "Impulse"], "img": ["JEOL", "Hamamatsu"]}


def _plugins_for(ext: str) -> list[dict]:
    import rsciio
    ps = [p for p in rsciio.IO_PLUGINS if ext in [e.lower() for e in p["file_extensions"]]]
    order = PREFERRED.get(ext, [])
    return sorted(ps, key=lambda p: order.index(p["name"]) if p["name"] in order else len(order))


def _signal(axes: list[dict], md_tree: dict) -> str:
    st = (md_tree.get("Signal") or {}).get("signal_type", "")
    nav = [a for a in axes if a.get("navigate")]
    if st in ("EDS_TEM", "EDS_SEM", "EELS") or any(a.get("units") in ("keV", "eV") for a in axes):
        return "spectrum_image" if nav else "spectrum"
    if any(str(a.get("units", "")).startswith("1/") for a in axes):
        return "diffraction"
    return "stack" if len(axes) == 3 and nav else "image"


def _normalize(tree: dict, orig: dict, plugin: str) -> dict:
    m = md.empty()
    ai = tree.get("Acquisition_instrument") or {}
    kind = next((k for k in ("TEM", "SEM") if k in ai), None)
    t = ai.get(kind, {}) if kind else {}
    if kind:
        m["technique"] = "STEM" if kind == "TEM" and (t.get("acquisition_mode") or "").upper() == "STEM" else kind
    md.put(m, "instrument.model", t.get("microscope"))
    md.put(m, "beam.voltage_kV", t.get("beam_energy"))
    md.put(m, "beam.current_nA", t.get("beam_current"))
    md.put(m, "optics.magnification", t.get("magnification"))
    md.put(m, "optics.camera_length_mm", t.get("camera_length"))
    md.put(m, "optics.working_distance_mm", t.get("working_distance"))
    det = t.get("Detector") or {}
    if det:
        md.put(m, "detector.name", ", ".join(det.keys()))
    stage = t.get("Stage") or {}
    for k, key in (("x_mm", "x"), ("y_mm", "y"), ("z_mm", "z"), ("tilt_deg", "tilt_alpha"), ("rotation_deg", "rotation")):
        if stage.get(key) is not None:
            md.put(m, f"sample.stage.{k}", stage[key])
    gen = tree.get("General") or {}
    if gen.get("date"):
        md.put(m, "acquisition.datetime", md.iso_datetime(gen.get('date'), gen.get('time')))
    md.put(m, "sample.name", (tree.get("Sample") or {}).get("description") or gen.get("title"))
    model = str(t.get("microscope") or "")
    vendor = {"EMD": "Thermo Fisher Scientific", "TIA": "Thermo Fisher Scientific",
              "JEOL": "JEOL", "Bruker": "Bruker", "EDAX": "EDAX (AMETEK)", "Phenom": "Thermo Fisher Scientific"}.get(plugin)
    if any(s in model for s in ("Titan", "Talos", "Themis", "Spectra", "Tecnai", "Helios", "Quanta", "Scios")):
        vendor = "Thermo Fisher Scientific"
    md.put(m, "instrument.vendor", vendor)
    return m


def _gatan(orig: dict, m: dict) -> dict:
    """Map Gatan Microscopy Suite ImageTags (Microscope Info, DigiScan, Session Info, EELS)."""
    try:
        groups = orig["ImageList"]
        tags = groups[sorted(groups)[-1]]["ImageTags"]   # last image holds the data in DM files
    except (KeyError, TypeError, IndexError):
        return m
    mi, ds, si = tags.get("Microscope Info", {}), tags.get("DigiScan", {}), tags.get("Session Info", {})
    scanning = mi.get("Illumination Mode") == "STEM" or mi.get("Operation Mode") == "SCANNING"
    m["technique"] = "STEM" if scanning else "TEM"
    v = mi.get("Voltage")
    md.put(m, "beam.voltage_kV", v / 1e3 if v else None)
    pc = mi.get("Probe Current (nA)")
    md.put(m, "beam.current_nA", pc if pc else None)
    md.put(m, "beam.probe_size_nm", mi.get("Probe Size (nm)") or None)
    md.put(m, "optics.magnification", mi.get("Indicated Magnification"))
    md.put(m, "optics.camera_length_mm", mi.get("STEM Camera Length") if scanning else mi.get("Camera Length"))
    md.put(m, "optics.field_of_view_um", mi.get("Field of View (µm)"))
    md.put(m, "optics.mode", mi.get("Imaging Mode"))
    md.put(m, "instrument.model", mi.get("Name") or mi.get("Microscope") or (si.get("Microscope") or None))
    md.put(m, "acquisition.dwell_us", ds.get("Sample Time"))
    md.put(m, "acquisition.frame_integration", ds.get("Number Summing Frames"))
    md.put(m, "acquisition.scan_rotation_deg", ds.get("Rotation"))
    md.put(m, "acquisition.operator", si.get("Operator") or None)
    md.put(m, "sample.name", si.get("Specimen") or None)
    gms = tags.get("GMS Version", {})
    md.put(m, "acquisition.software", "Gatan Microscopy Suite " + str(gms.get("Created", "")).strip())
    eels = tags.get("EELS", {})
    if eels:
        ec, ea = eels.get("Experimental Conditions", {}), eels.get("Acquisition", {})
        md.put(m, "detector.name", "EELS")
        md.put(m, "detector.collection_semiangle_mrad", ec.get("Collection semi-angle (mrad)"))
        md.put(m, "detector.convergence_semiangle_mrad", ec.get("Convergence semi-angle (mrad)"))
        md.put(m, "detector.exposure_s", ea.get("Exposure (s)"))
    return m


def read_rsciio(path: Path, lazy: bool = False) -> Optional[list[Dataset]]:
    try:
        import rsciio  # noqa: F401
    except ImportError as e:
        raise ImportError("Install RosettaSciIO for this format: pip install rosettasciio") from e
    errors = []
    for p in _plugins_for(path.suffix.lower().lstrip(".")):
        try:
            mod = importlib.import_module(p["api"])
            items = mod.file_reader(str(path), lazy=lazy)
        except Exception as e:  # try the next plugin for ambiguous extensions
            errors.append(f"{p['name']}: {e}")
            continue
        out = []
        for i, it in enumerate(items):
            axes = [Axis(name=str(a.get("name") or f"axis{k}"), size=int(a.get("size", n)),
                         scale=float(a.get("scale", 1.0) or 1.0), units=str(a.get("units") or "px"),
                         offset=float(a.get("offset", 0.0) or 0.0), navigate=bool(a.get("navigate", False)))
                    for k, (a, n) in enumerate(zip(it["axes"], np.shape(it["data"])))]
            tree = it.get("metadata") or {}
            name = (tree.get("General") or {}).get("title") or path.stem
            orig = dict(it.get("original_metadata") or {})
            orig["_reader"] = p["name"].lower().replace(" ", "_")
            meta = _normalize(tree, orig, p["name"])
            if p["name"] == "DigitalMicrograph":
                meta = _gatan(orig, meta)
            out.append(Dataset(it["data"], axes, metadata=meta,
                               original_metadata=orig, name=f"{name}" if len(items) == 1 else f"{name}[{i}]",
                               signal=_signal(it["axes"], tree)))
        return out
    if errors:
        raise ValueError(f"Could not read {path.name}: " + "; ".join(errors))
    return None


__all__ = ["read_rsciio"]
