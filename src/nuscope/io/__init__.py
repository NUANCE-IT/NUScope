"""Reading and saving NUANCE data.

``load(source)`` accepts a local path or a ``globus://<collection>/<path>`` URL and
returns a :class:`~nuscope.Dataset` with calibrated axes, normalized
metadata and provenance (the source file's SHA-256, where it came from, who
read it and with which software).

Formats:

* NUANCE SEM/FIB TIFFs (Thermo Fisher/FEI, Zeiss, Hitachi, JEOL), read natively;
* 40+ electron-microscopy formats through RosettaSciIO: Gatan DM3/DM4,
  Thermo Fisher Velox EMD, TIA SER/EMI, JEOL, Bruker BCF, EDAX, MRC, MIB,
  Delmic, PantaRhei, ...;
* NUScope's own files: NeXus/HDF5 ``.nxs``, Zarr ``.zarr`` and TIFF with
  embedded metadata, all carrying the full provenance.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np

from .. import metadata as md
from ..dataset import Axis, Dataset
from ..provenance import Provenance, now

NUSCOPE_EXT = {".nxs", ".nsh5"}
TIFF_PREFIX = "NUScope dataset v1\n"


# ------------------------------------------------------------------ load
def load(source, *, crop_databar: bool = True, lazy: bool = False, index: int = 0, **kw) -> Dataset:
    """Load one dataset (the ``index``-th if the file holds several)."""
    items = load_all(source, crop_databar=crop_databar, lazy=lazy, **kw)
    return items[index]


def load_all(source, *, crop_databar: bool = True, lazy: bool = False, **kw) -> list[Dataset]:
    s = str(source)
    if s.startswith("globus://"):
        from ..globus import fetch
        local, entity = fetch(s, **{k: v for k, v in kw.items() if k in ("session", "cache_dir")})
        items = load_all(local, crop_databar=crop_databar, lazy=lazy)
        for d in items:
            d.provenance.entities[entity.id] = entity
            d.provenance.activities[-1].used.append(entity.id)
        return items
    path = Path(s).expanduser()
    if not path.exists():
        raise FileNotFoundError(path)
    started = now()
    ext = path.suffix.lower()
    if ext in NUSCOPE_EXT or (ext in (".h5", ".hdf5") and _is_nuscope_h5(path)):
        return [read_nexus(path)]
    if ext == ".zarr" or (path.is_dir() and (path / "zarr.json").exists()):
        return [read_zarr(path)]
    if ext == ".npy":
        return [_finish(Dataset.from_array(np.load(path), name=path.stem), path, "io.read.npy", {}, started)]
    if ext in (".tif", ".tiff"):
        if _is_nuscope_tiff(path):
            return [read_nuscope_tiff(path)]
        from .vendor import read_vendor_tiff
        got = read_vendor_tiff(path, crop_databar=crop_databar)
        if got is not None:
            img, meta, raw, (py, px), vendor = got
            axes = [Axis("y", img.shape[0], py or 1.0, "nm" if py else "px"),
                    Axis("x", img.shape[1], px or 1.0, "nm" if px else "px")]
            if img.ndim == 3:
                axes = [Axis("channel", img.shape[0])] + axes if img.shape[0] < img.shape[-1] else axes + [Axis("channel", img.shape[2])]
            ds = Dataset(img, axes, metadata=meta, original_metadata=raw, name=path.stem)
            return [_finish(ds, path, f"io.read.{vendor}", {"crop_databar": crop_databar}, started)]
    from .rsciio_backend import read_rsciio
    out = read_rsciio(path, lazy=lazy)
    if out is None:
        raise ValueError(f"No reader for {path.name}. Supported: {', '.join(formats())}")
    return [_finish(d, path, f"io.read.{d.original_metadata.get('_reader', 'rsciio')}", {"lazy": lazy}, started)
            for d in out]


def _finish(ds: Dataset, path: Path, op: str, params: dict, started: str) -> Dataset:
    p = Provenance()
    src = p.add_file(path)
    inst = p.add_instrument(ds.metadata)
    out = p.add_array(ds.data if not hasattr(ds.data, "compute") else np.zeros(1), label=ds.name)
    p.record(op, params, used=[src], generated=[out], started=started, instrument=inst)
    ds.provenance = p
    ds.metadata.setdefault("facility", md.empty()["facility"])
    return ds


def formats() -> list[str]:
    out = ["Thermo Fisher/FEI TIFF", "Zeiss TIFF", "Hitachi TIFF+TXT", "JEOL TIFF+TXT", "NUScope .nxs/.zarr/.tif"]
    try:
        import rsciio
        out += [p["name"] for p in rsciio.IO_PLUGINS]
    except ImportError:
        pass
    return out


# ------------------------------------------------------------------ NeXus / HDF5
def save(ds: Dataset, path, *, overwrite: bool = False, compression: Optional[str] = "gzip") -> Path:
    """Save to .nxs (NeXus/HDF5), .zarr or .tif; provenance is recorded and embedded."""
    path = Path(path)
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} exists (pass overwrite=True)")
    ext = path.suffix.lower()
    if ext not in (".nxs", ".h5", ".hdf5", ".nsh5", ".zarr", ".tif", ".tiff"):
        raise ValueError("save to .nxs, .h5, .zarr or .tif")
    path.parent.mkdir(parents=True, exist_ok=True)
    started = now()
    ds.provenance.record(f"io.save{ext}", {"path": path.name}, used=[ds.provenance.current] if ds.provenance.current else [],
                         started=started)
    if ext in (".nxs", ".h5", ".hdf5", ".nsh5"):
        _write_nexus(ds, path, compression)
    elif ext == ".zarr":
        _write_zarr(ds, path)
    elif ext in (".tif", ".tiff"):
        _write_tiff(ds, path)
    return path


def _doc(ds: Dataset) -> dict:
    return {"name": ds.name, "signal": ds.signal,
            "axes": [vars(a) for a in ds.axes], "metadata": ds.metadata,
            "original_metadata": ds.original_metadata, "provenance": ds.provenance.to_dict()}


def _j(o) -> str:
    from ..provenance import _jsonable
    return json.dumps(_jsonable(o))


def _write_nexus(ds: Dataset, path: Path, compression):
    import h5py
    with h5py.File(path, "w") as f:
        f.attrs.update({"NX_class": "NXroot", "creator": "NUScope", "default": "entry"})
        e = f.create_group("entry")
        e.attrs.update({"NX_class": "NXentry", "default": "data"})
        e["title"] = ds.name or "dataset"
        e["definition"] = "NXem" if ds.metadata.get("technique") in ("SEM", "TEM", "STEM", "FIB") else "NXdata"
        d = e.create_group("data")
        d.attrs.update({"NX_class": "NXdata", "signal": "data", "axes": [a.name for a in ds.axes]})
        d.create_dataset("data", data=ds.numpy(), compression=compression, chunks=True)
        for i, a in enumerate(ds.axes):
            ax = d.create_dataset(a.name, data=a.values())
            ax.attrs["units"] = a.units
            d.attrs[f"{a.name}_indices"] = i
        ins = e.create_group("instrument")
        ins.attrs["NX_class"] = "NXinstrument"
        for k, v in (ds.metadata.get("instrument") or {}).items():
            ins.attrs[k] = str(v)
        for sec in ("beam", "optics", "detector", "acquisition", "sample"):
            g = ins.create_group(sec)
            for k, v in (ds.metadata.get(sec) or {}).items():
                g.attrs[k] = v if isinstance(v, (int, float, str)) else json.dumps(v, default=str)
        n = e.create_group("nuscope")
        n.attrs["NX_class"] = "NXcollection"
        doc = _doc(ds)
        for k in ("metadata", "original_metadata", "provenance"):
            n[k] = _j(doc[k])
        n["axes"] = _j(doc["axes"])
        n.attrs.update({"name": ds.name, "signal": ds.signal})


def _is_nuscope_h5(path: Path) -> bool:
    try:
        import h5py
        with h5py.File(path, "r") as f:
            return "entry/nuscope" in f
    except Exception:
        return False


def _from_doc(data, n: dict) -> Dataset:
    return Dataset(data, [Axis(**a) for a in n["axes"]], metadata=n["metadata"],
                   original_metadata=n.get("original_metadata", {}),
                   provenance=Provenance.from_dict(n["provenance"]), name=n.get("name", ""),
                   signal=n.get("signal", "image"))


def read_nexus(path: Path) -> Dataset:
    import h5py
    with h5py.File(path, "r") as f:
        n = f["entry/nuscope"]
        doc = {k: json.loads(n[k][()]) for k in ("metadata", "original_metadata", "provenance", "axes")}
        doc.update(name=n.attrs.get("name", ""), signal=n.attrs.get("signal", "image"))
        data = f["entry/data/data"][()]
    ds = _from_doc(data, doc)
    _record_reopen(ds, path)
    return ds


def _record_reopen(ds: Dataset, path: Path):
    eid = ds.provenance.add_file(path)
    ds.provenance.record("io.read.nuscope", {}, used=[eid], generated=[ds.provenance.current or eid])


# ------------------------------------------------------------------ Zarr
def _write_zarr(ds: Dataset, path: Path):
    import zarr
    root = zarr.open_group(str(path), mode="w")
    arr = root.create_array("data", shape=ds.shape, dtype=ds.dtype, chunks=tuple(min(s, 512) for s in ds.shape))
    arr[...] = ds.numpy()
    root.attrs["nuscope"] = json.loads(_j(_doc(ds)))


def read_zarr(path: Path) -> Dataset:
    import zarr
    root = zarr.open_group(str(path), mode="r")
    ds = _from_doc(np.asarray(root["data"][...]), dict(root.attrs["nuscope"]))
    _record_reopen(ds, path) if path.is_file() else ds.provenance.record("io.read.zarr", {"path": path.name})
    return ds


# ------------------------------------------------------------------ TIFF with metadata
def _write_tiff(ds: Dataset, path: Path):
    import tifffile
    ps = ds.pixel_size_nm
    kw = {"resolution": (1e7 / ps, 1e7 / ps), "resolutionunit": "CENTIMETER"} if ps else {}
    # a plain-text prefix keeps tifffile from treating the JSON as its own "shaped" description
    tifffile.imwrite(path, ds.numpy(), description=TIFF_PREFIX + _j(_doc(ds)), metadata=None, **kw)


def _is_nuscope_tiff(path: Path) -> bool:
    import tifffile
    try:
        with tifffile.TiffFile(path) as t:
            return t.pages[0].description.startswith(TIFF_PREFIX)
    except Exception:
        return False


def read_nuscope_tiff(path: Path) -> Dataset:
    import tifffile
    with tifffile.TiffFile(path) as t:
        doc = json.loads(t.pages[0].description[len(TIFF_PREFIX):])
        data = t.asarray()
    ds = _from_doc(data, doc)
    _record_reopen(ds, path)
    return ds


__all__ = ["load", "load_all", "save", "formats", "read_nexus", "read_zarr"]
