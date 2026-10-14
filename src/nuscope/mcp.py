"""NUScope inside NUANCE-MCP: data tools for the LLM, and sealed files for every acquisition.

NUANCE-MCP (https://github.com/NUANCE-IT/NUANCE-MCP) loads this module through
the ``nuance_mcp.plugins`` entry point. ``register(ctx)`` then

* saves every acquisition (``acquire_tem_image``, ``acquire_stem``,
  ``acquire_4d_stem``, ``acquire_diffraction``, ``acquire_eels``) as a NUScope
  ``.h5`` file: calibrated axes, the column state as metadata, the tool call
  and its parameters as provenance, sealed with SHA-256 hashes and signed with
  your EMDataBridge identity when you have one. The tool response gains
  ``plugins.nuscope = {"file", "seal", "signed_by", ...}``;
* adds tools that work on files, so the model can read, check and analyse data
  with calibrated units: ``nuscope_describe``, ``nuscope_verify``,
  ``nuscope_analyze``, ``nuscope_history``, ``nuscope_list``, ``nuscope_identity``.

Files go to ``$NUSCOPE_ACQUISITION_DIR`` (default ``~/NUScope/acquisitions``),
one folder per day. Set ``NUSCOPE_SAMPLE`` to record the sample name.

NUScope does not import NUANCE-MCP: the acquisition results are read by their
attributes (``data``, ``pixel_size_nm``, ``tags`` ... or ``counts``, ``energy_eV``).
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np

from . import __version__
from . import analyze as an
from . import metadata as md
from .dataset import Axis, Dataset
from .io import load, save
from .integrity import my_key, verify
from .provenance import Agent, _jsonable

TECHNIQUE = {"acquire_tem_image": "TEM", "acquire_stem": "STEM", "acquire_4d_stem": "4D-STEM",
             "acquire_diffraction": "TEM", "acquire_eels": "EELS"}
SIGNAL = {"acquire_tem_image": "image", "acquire_stem": "image", "acquire_4d_stem": "diffraction",
          "acquire_diffraction": "diffraction", "acquire_eels": "spectrum"}

OPS = {"stats": an.stats, "denoise": an.denoise, "subtract_background": an.subtract_background,
       "fft": an.fft, "radial_profile": an.radial_profile, "line_profile": an.line_profile,
       "particles": an.particles, "threshold": an.threshold, "calibrate": an.calibrate,
       "crop": an.crop, "bin": an.bin_image}


def acquisition_dir() -> Path:
    base = Path(os.environ.get("NUSCOPE_ACQUISITION_DIR", Path.home() / "NUScope" / "acquisitions")).expanduser()
    return base / datetime.now().strftime("%Y-%m-%d")


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_")[:60] or "acquisition"


def _metadata(tool: str, params: dict, result: Any, instrument: dict) -> dict:
    m = md.empty()
    st = instrument.get("state") or {}
    md.put(m, "instrument.vendor", instrument.get("vendor"))
    md.put(m, "instrument.model", instrument.get("model"))
    m["technique"] = TECHNIQUE.get(tool)
    md.put(m, "beam.voltage_kV", st.get("high_tension_kV"))
    md.put(m, "beam.spot_size", st.get("spot_size"))
    md.put(m, "optics.magnification", st.get("magnification"))
    md.put(m, "optics.mode", st.get("mode") or st.get("illumination_mode"))
    md.put(m, "optics.focus_um", st.get("focus_um"))
    md.put(m, "optics.camera_length_mm", params.get("camera_length_mm"))
    md.put(m, "optics.convergence_mrad", params.get("convergence_mrad"))
    for ax in ("x", "y", "z"):
        md.put(m, f"sample.stage_{ax}_um", st.get(f"stage_{ax}_um"))
    md.put(m, "sample.stage_alpha_deg", st.get("stage_alpha_deg"))
    md.put(m, "sample.name", os.environ.get("NUSCOPE_SAMPLE"))
    md.put(m, "acquisition.datetime", datetime.now().astimezone().isoformat(timespec="seconds"))
    md.put(m, "acquisition.dwell_us", params.get("dwell_us"))
    md.put(m, "acquisition.exposure_s", getattr(result, "exposure_s", None) or params.get("exposure_s"))
    md.put(m, "acquisition.software", "NUANCE-MCP")
    me = my_key()
    md.put(m, "acquisition.operator", me.name if me else None)
    if st.get("detector_state"):
        m["detector"] = {"state": st["detector_state"]}
    return m


def dataset_from_acquisition(tool: str, params: dict, result: Any, instrument: dict) -> Dataset:
    """A calibrated NUScope dataset from a NUANCE-MCP ImageReturn / SpectrumReturn, with provenance."""
    meta = _metadata(tool, params, result, instrument)
    name = getattr(result, "name", None) or tool
    if hasattr(result, "counts"):                     # SpectrumReturn
        e = np.asarray(result.energy_eV, dtype=float)
        disp = getattr(result, "dispersion_eV_per_ch", None) or (float(e[1] - e[0]) if e.size > 1 else 1.0)
        data = np.asarray(result.counts)
        axes = [Axis("energy", data.size, disp, "eV", float(e[0]) if e.size else 0.0)]
    else:                                             # ImageReturn
        data = np.asarray(result.data)
        unit = getattr(result, "pixel_unit", "nm") or "nm"
        ps = getattr(result, "pixel_size_nm", None)
        scale = md.to_nm(ps, unit) if ps is not None else None
        if ps is not None and scale is None:          # reciprocal or angular units: keep them
            sc, u = float(ps), unit
        else:
            sc, u = (scale, "nm") if scale else (1.0, "px")
        if data.ndim == 4:
            names = ["scan_y", "scan_x", "ky", "kx"]
        else:
            names = [f"axis{i}" for i in range(data.ndim - 2)] + ["y", "x"]
        axes = [Axis(n, s) for n, s in zip(names, data.shape)]
        if data.ndim == 4:                            # scan calibrated, detector in pixels
            for a in axes[:2]:
                a.scale, a.units, a.navigate = sc, u, True
        else:
            for a in axes[-2:]:
                a.scale, a.units = sc, u
    ds = Dataset(data, axes, metadata=meta, original_metadata={"nuance_mcp": {"tool": tool, "params": params,
                                                                            "tags": getattr(result, "tags", {}),
                                                                            "instrument": instrument}},
                 name=_slug(name), signal=SIGNAL.get(tool, "image"))
    p = ds.provenance
    inst = p.add_instrument(meta)
    p.add_agent(Agent(id="software:nuance-mcp", kind="software", name="NUANCE-MCP"))
    out = p.add_array(data, label=ds.name)
    p.record(f"acquire.{tool}", params, used=[], generated=[out], instrument=inst)
    return ds


def _on_acquisition(tool: str, params: dict, result: Any, instrument: dict) -> dict:
    ds = dataset_from_acquisition(tool, params, result, instrument)
    folder = acquisition_dir()
    path = folder / f"{datetime.now().strftime('%H%M%S_%f')[:-3]}_{_slug(tool)}_{ds.name}.h5"
    save(ds, path)
    r = verify(path)
    return {"file": str(path), "seal": r.seal_id, "integrity": r.status,
            "signed_by": [f"{s['name']} [{s['fingerprint']}]" for s in r.signatures if s["valid"]],
            "hint": "Open it with nuscope_describe / nuscope_analyze, or in NUScope Studio."}


# ------------------------------------------------------------------ tools
def _plain(obj):
    """JSON-safe tool output: numpy -> Python, NaN/inf -> None."""
    import math

    def fix(v):
        if isinstance(v, float) and not math.isfinite(v):
            return None
        if isinstance(v, dict):
            return {k: fix(x) for k, x in v.items()}
        if isinstance(v, list):
            return [fix(x) for x in v]
        return v
    return fix(_jsonable(obj))


def _tool(fn):
    """Return plain JSON from a tool, keeping the signature FastMCP reads."""
    import functools

    @functools.wraps(fn)
    def inner(*a, **kw):
        return _plain(fn(*a, **kw))
    return inner


def _describe(ds: Dataset) -> dict:
    return {"name": ds.name, "signal": ds.signal, "shape": list(ds.shape), "dtype": str(ds.dtype),
            "axes": [{"name": a.name, "size": a.size, "scale": a.scale, "units": a.units} for a in ds.axes],
            "summary": md.summary(ds.metadata),
            "integrity": ds.integrity.status if ds.integrity is not None else "not a NUScope file",
            "history_steps": len(ds.provenance.activities)}


def _table(df, limit: int = 20) -> dict:
    return {"rows": len(df), "columns": list(df.columns),
            "head": df.head(limit).to_dict(orient="records"),
            "describe": df.describe().round(4).to_dict() if len(df) else {}}


def register(ctx) -> None:
    """Entry point for NUANCE-MCP (``nuance_mcp.plugins``)."""
    ctx.on_acquisition(_on_acquisition)
    mcp = ctx.mcp

    @mcp.tool(name="nuscope_describe")
    @_tool
    def nuscope_describe(path: str) -> dict:
        """Read any microscope file NUScope supports (Gatan, Thermo Fisher, Zeiss, Hitachi, JEOL, NUScope .h5 ...)
        and return its calibration, key metadata and integrity status."""
        return _describe(load(path))

    @mcp.tool(name="nuscope_verify")
    @_tool
    def nuscope_verify(path: str) -> dict:
        """Check a NUScope file's seal: data, calibration, metadata and history unchanged, and who signed it."""
        return verify(path).to_dict()

    @mcp.tool(name="nuscope_history")
    @_tool
    def nuscope_history(path: str) -> dict:
        """The provenance of a file: every step with its parameters, and its source files with SHA-256."""
        ds = load(path)
        return {"steps": ds.provenance.lineage(),
                "sources": [{"file": e.label, "sha256": e.sha256, "location": e.location}
                            for e in ds.provenance.sources()]}

    @mcp.tool(name="nuscope_analyze")
    @_tool
    def nuscope_analyze(path: str, op: str, params: Optional[dict] = None) -> dict:
        """Analyse a file in physical units. op is one of: stats, denoise, subtract_background, fft,
        radial_profile, line_profile (params start=[y,x], end=[y,x]), particles, threshold, calibrate
        (pixel_size_nm, reason), crop, bin. Image results are saved as new sealed .h5 files next to the
        input, with the full history; tables are returned as a summary."""
        if op not in OPS:
            return {"error": f"unknown op {op!r}", "ops": sorted(OPS)}
        ds = load(path)
        out = OPS[op](ds, **(params or {}))
        if isinstance(out, Dataset):
            dest = Path(path).with_name(f"{Path(path).stem}_{op}.h5")
            n = 1
            while dest.exists():
                n += 1
                dest = Path(path).with_name(f"{Path(path).stem}_{op}_{n}.h5")
            save(out, dest)
            return {"file": str(dest), **_describe(load(dest))}
        if hasattr(out, "to_dict"):
            res = _table(out)
            res.update({k: v for k, v in getattr(out, "attrs", {}).items() if isinstance(v, (int, float, str))})
            return res
        return {"result": out}

    @mcp.tool(name="nuscope_list")
    @_tool
    def nuscope_list(folder: Optional[str] = None) -> dict:
        """Files NUScope saved from acquisitions (today by default), newest first."""
        base = Path(folder).expanduser() if folder else acquisition_dir()
        files = sorted(base.glob("*.h5"), key=lambda p: p.stat().st_mtime, reverse=True) if base.exists() else []
        return {"folder": str(base), "files": [p.name for p in files[:200]]}

    @mcp.tool(name="nuscope_identity")
    @_tool
    def nuscope_identity() -> dict:
        """Who signs the data saved from this session (EMDataBridge identity), and where files are saved."""
        me = my_key()
        return {"signer": str(me) if me else None, "orcid": me.orcid if me else None,
                "acquisition_dir": str(acquisition_dir()), "nuscope": __version__,
                "note": None if me else 'Files are sealed but not signed; run: emdb identity create "Name" --orcid ...'}


__all__ = ["register", "dataset_from_acquisition", "acquisition_dir"]
