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
* NUScope's own files: NeXus/HDF5 ``.nxs`` or ``.h5``, Zarr ``.zarr`` and TIFF
  with embedded metadata, all carrying the full provenance and a cryptographic
  seal (see :mod:`nuscope.integrity`) that is checked on every read.
"""
from __future__ import annotations

import json
import warnings
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
    """Load one dataset (the ``index``-th if the file holds several).

    NUScope files are verified against their seal; the report is in ``ds.integrity``."""
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
            d.provenance.amend_last(used=[entity.id])
        return items
    path = Path(s).expanduser()
    if not path.exists():
        raise FileNotFoundError(2, "No such file", str(path))
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
def save(ds: Dataset, path, *, overwrite: bool = False, compression: Optional[str] = "gzip",
         sign: Optional[bool] = None) -> Path:
    """Save to .nxs or .h5 (NeXus/HDF5), .zarr or .tif, with metadata, provenance and a seal.

    The seal holds SHA-256 hashes of data, calibration, metadata and history.
    ``sign=None`` also signs it when you have a key (``nuscope keys create``),
    ``True`` requires a key and ``False`` leaves it unsigned."""
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
    from ..integrity import make_seal
    data = ds.numpy()
    doc = json.loads(_j(_doc(ds)))
    doc["seal"] = make_seal(data, doc, sign=sign)
    if ext in (".nxs", ".h5", ".hdf5", ".nsh5"):
        _write_nexus(ds, data, doc, path, compression)
    elif ext == ".zarr":
        _write_zarr(data, doc, path)
    elif ext in (".tif", ".tiff"):
        _write_tiff(ds, data, doc, path)
    return path


def _doc(ds: Dataset) -> dict:
    return {"name": ds.name, "signal": ds.signal,
            "axes": [vars(a) for a in ds.axes], "metadata": ds.metadata,
            "original_metadata": ds.original_metadata, "provenance": ds.provenance.to_dict()}


def _j(o) -> str:
    from ..provenance import _jsonable
    return json.dumps(_jsonable(o))


def _write_nexus(ds: Dataset, data, doc: dict, path: Path, compression):
    import h5py
    from ..integrity import seal_id
    with h5py.File(path, "w") as f:
        f.attrs.update({"NX_class": "NXroot", "creator": "NUScope", "default": "entry"})
        _seal_attrs(f, doc["seal"])
        e = f.create_group("entry")
        e.attrs.update({"NX_class": "NXentry", "default": "data"})
        e["title"] = ds.name or "dataset"
        e["definition"] = "NXem" if ds.metadata.get("technique") in ("SEM", "TEM", "STEM", "FIB") else "NXdata"
        d = e.create_group("data")
        d.attrs.update({"NX_class": "NXdata", "signal": "data", "axes": [a.name for a in ds.axes]})
        dd = d.create_dataset("data", data=data, compression=compression, chunks=True if data.ndim else None)
        dd.attrs["sha256"] = doc["seal"]["manifest"]["data"]["sha256"]
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
        for k in ("metadata", "original_metadata", "provenance", "axes", "seal"):
            n[k] = json.dumps(doc[k])
        n.attrs.update({"name": doc["name"], "signal": doc["signal"], "seal_id": seal_id(doc["seal"])})


def _seal_attrs(f, seal: dict):
    """Readable summary at the file root, for anyone opening it in HDFView or h5py."""
    from ..integrity import seal_id
    f.attrs["nuscope_seal"] = seal_id(seal)
    f.attrs["nuscope_signed_by"] = "; ".join(
        f"{s['signer']['name']} [{s['signer']['fingerprint']}]" for s in seal.get("signatures", [])) or "unsigned"


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


def _nexus_document(path: Path):
    import h5py
    with h5py.File(path, "r") as f:
        n = f["entry/nuscope"]
        doc = {k: json.loads(n[k][()]) for k in ("metadata", "original_metadata", "provenance", "axes", "seal")
               if k in n}
        doc.update(name=_str(n.attrs.get("name", "")), signal=_str(n.attrs.get("signal", "image")))
        data = f["entry/data/data"][()]
    return data, doc


def _str(v) -> str:
    return v.decode() if isinstance(v, bytes) else str(v)


def read_nexus(path: Path) -> Dataset:
    return _open_document(path, *_nexus_document(path))


def _open_document(path: Path, data, doc: dict) -> Dataset:
    from ..integrity import verify_doc
    report = verify_doc(data, doc)
    ds = _from_doc(data, doc)
    ds.integrity = report
    if report.status == "tampered":
        warnings.warn(f"{path.name} changed after it was sealed: " + "; ".join(report.problems), stacklevel=3)
    eid = ds.provenance.add_file(path, hash_file=path.is_file())   # a .zarr store is a folder; its seal pins the content
    ds.provenance.record("io.read.nuscope", {"integrity": report.status, "seal": report.seal_id,
                                             "signed_by": [s["fingerprint"] for s in report.signatures if s["valid"]]},
                         used=[eid], generated=[ds.provenance.current or eid])
    return ds


def read_document(path: Path):
    """The array and the NUScope document (metadata, axes, provenance, seal) of a NUScope file, untouched."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".zarr" or (path.is_dir() and (path / "zarr.json").exists()):
        return _zarr_document(path)
    if ext in (".tif", ".tiff"):
        return _tiff_document(path)
    return _nexus_document(path)


def write_seal(path: Path, seal: dict):
    """Replace the seal of a NUScope file (used to add signatures; the manifest itself never changes)."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".zarr" or path.is_dir():
        import zarr
        root = zarr.open_group(str(path), mode="r+")
        doc = dict(root.attrs["nuscope"])
        doc["seal"] = seal
        root.attrs["nuscope"] = doc
    elif ext in (".tif", ".tiff"):
        import tifffile
        _, doc = _tiff_document(path)
        doc["seal"] = seal
        tifffile.tiffcomment(path, comment=TIFF_PREFIX + json.dumps(doc))
    else:
        import h5py
        from ..integrity import seal_id
        with h5py.File(path, "r+") as f:
            n = f["entry/nuscope"]
            del n["seal"]
            n["seal"] = json.dumps(seal)
            n.attrs["seal_id"] = seal_id(seal)
            _seal_attrs(f, seal)


# ------------------------------------------------------------------ Zarr
def _write_zarr(data, doc: dict, path: Path):
    import zarr
    root = zarr.open_group(str(path), mode="w")
    arr = root.create_array("data", shape=data.shape, dtype=data.dtype, chunks=tuple(min(s, 512) for s in data.shape))
    arr[...] = data
    root.attrs["nuscope"] = doc


def _zarr_document(path: Path):
    import zarr
    root = zarr.open_group(str(path), mode="r")
    return np.asarray(root["data"][...]), dict(root.attrs["nuscope"])


def read_zarr(path: Path) -> Dataset:
    return _open_document(path, *_zarr_document(path))


# ------------------------------------------------------------------ TIFF with metadata
def _write_tiff(ds: Dataset, data, doc: dict, path: Path):
    import tifffile
    ps = ds.pixel_size_nm
    kw = {"resolution": (1e7 / ps, 1e7 / ps), "resolutionunit": "CENTIMETER"} if ps else {}
    # a plain-text prefix keeps tifffile from treating the JSON as its own "shaped" description
    tifffile.imwrite(path, data, description=TIFF_PREFIX + json.dumps(doc), metadata=None, **kw)


def _is_nuscope_tiff(path: Path) -> bool:
    import tifffile
    try:
        with tifffile.TiffFile(path) as t:
            return t.pages[0].description.startswith(TIFF_PREFIX)
    except Exception:
        return False


def _tiff_document(path: Path):
    import tifffile
    with tifffile.TiffFile(path) as t:
        doc = json.loads(t.pages[0].description[len(TIFF_PREFIX):])
        data = t.asarray()
    shape = tuple(a["size"] for a in doc["axes"])
    if data.shape != shape and data.size == int(np.prod(shape)):   # TIFF pages flatten leading axes
        data = data.reshape(shape)
    return data, doc


def read_nuscope_tiff(path: Path) -> Dataset:
    return _open_document(path, *_tiff_document(path))


__all__ = ["load", "load_all", "save", "formats", "read_nexus", "read_zarr", "read_document", "write_seal"]
