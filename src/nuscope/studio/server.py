"""NUScope Studio backend.

Serves a data folder (and Globus collections) to the browser UI: a file
library, calibrated image rendering, spectrum / 4D picks, analysis runs,
saving, figure export, provenance and RO-Crate packaging. Data stays on the
machine running the server; the browser receives rendered images and tables.
"""
from __future__ import annotations

import io
import json
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .. import __version__, analyze as an, metadata as md
from ..dataset import Dataset
from ..io import load_all, save

STATIC = Path(__file__).parent / "static"
DATA_EXT = {".tif", ".tiff", ".dm3", ".dm4", ".emd", ".ser", ".emi", ".mrc", ".ali", ".bcf", ".spx", ".spd", ".spc",
            ".nxs", ".h5", ".hdf5", ".hspy", ".zspy", ".mib", ".img", ".map", ".pts", ".asw", ".png", ".jpg", ".jpeg",
            ".npy", ".blo", ".prz", ".elid", ".tvips", ".unf", ".msa", ".emsa"}
SPECTRAL_UNITS = {"ev", "kev", "mev"}

OPS = {
    "stats": an.stats, "denoise": an.denoise, "subtract_background": an.subtract_background, "fft": an.fft,
    "radial_profile": an.radial_profile, "line_profile": an.line_profile, "particles": an.particles,
    "threshold": an.threshold, "calibrate": an.calibrate, "crop": an.crop, "bin": an.bin_image,
}


@dataclass
class Item:
    id: str
    ds: Dataset
    parent: Optional[str] = None
    op: Optional[str] = None
    cache: dict = field(default_factory=dict)
    source: Optional[str] = None   # file or URL it was opened from (top-level items only)


def _jsonable(o: Any):
    from ..provenance import _jsonable as j
    return j(o)


def view_of(ds: Dataset) -> dict:
    """How to show a dataset: which axes form the image and what a click picks."""
    units = [a.units.lower() for a in ds.axes]
    spectral = [i for i, u in enumerate(units) if u in SPECTRAL_UNITS or "energy" in ds.axes[i].name.lower()]
    recip = [i for i, u in enumerate(units) if u.startswith("1/")]
    nd = ds.ndim
    if nd == 1:
        return {"kind": "spectrum", "axis": 0}
    if nd == 2:
        return {"kind": "image", "image_axes": [0, 1]}
    if nd == 3 and len(spectral) == 1:
        img = [i for i in range(3) if i != spectral[0]]
        return {"kind": "spectrum_image", "image_axes": img, "signal_axes": spectral}
    if nd == 3:
        return {"kind": "stack", "image_axes": [1, 2], "frame_axis": 0, "frames": ds.shape[0]}
    if nd == 4:
        sig = recip if len(recip) == 2 else [2, 3]
        img = [i for i in range(4) if i not in sig]
        return {"kind": "4d", "image_axes": img, "signal_axes": sig}
    return {"kind": "unsupported"}


def image_of(item: Item, frame: int = 0) -> np.ndarray:
    ds, v = item.ds, view_of(item.ds)
    key = ("img", frame)
    if key in item.cache:
        return item.cache[key]
    a = ds.numpy()
    if v["kind"] == "image":
        img = a
    elif v["kind"] == "stack":
        img = a[min(max(frame, 0), a.shape[0] - 1)]
    elif v["kind"] in ("spectrum_image", "4d"):
        img = a.astype(np.float64).sum(axis=tuple(v["signal_axes"]))
    else:
        raise HTTPException(400, "nothing to display as an image")
    if img.ndim == 3 and img.shape[-1] in (3, 4):
        img = img[..., :3].mean(-1)
    img = np.asarray(img, dtype=np.float64)
    if len(item.cache) > 40:
        item.cache.clear()
    item.cache[key] = img
    return img


def to_u8(img: np.ndarray, lo: float, hi: float, gamma: float = 1.0, log: bool = False) -> np.ndarray:
    a = img
    if log:
        off = min(0.0, float(np.nanmin(a)))
        a = np.log1p(a - off)
        lo, hi = np.log1p(lo - off), np.log1p(hi - off)
    u = np.clip((a - lo) / ((hi - lo) or 1.0), 0, 1)
    if gamma != 1.0:
        u = u ** gamma
    return (u * 255 + 0.5).astype(np.uint8)


def png(a: np.ndarray) -> bytes:
    import imageio.v3 as iio
    return iio.imwrite("<bytes>", a, extension=".png")


def summary_of(item: Item) -> dict:
    ds = item.ds
    prov = ds.provenance
    return {
        "id": item.id, "name": ds.name, "parent": item.parent, "op": item.op, "shape": list(ds.shape),
        "dtype": str(ds.dtype), "signal": ds.signal, "view": view_of(ds), "pixel_size_nm": ds.pixel_size_nm,
        "axes": [vars(a) for a in ds.axes], "metadata": _jsonable(ds.metadata), "summary": md.summary(ds.metadata),
        "sources": [vars(e) for e in prov.sources()],
        "activities": [vars(a) for a in prov.activities], "agents": [vars(a) for a in prov.agents.values()],
    }


def _trim(o, depth=0, max_items=200):
    """Original metadata can be huge (arrays, thousands of tags): keep it browsable."""
    if depth > 8:
        return "…"
    if isinstance(o, dict):
        items = list(o.items())[:max_items]
        return {str(k): _trim(v, depth + 1) for k, v in items}
    if isinstance(o, (list, tuple)):
        return [_trim(v, depth + 1) for v in o[:50]] + (["…"] if len(o) > 50 else [])
    if hasattr(o, "shape") and getattr(o, "size", 0) > 50:
        return f"<array {tuple(o.shape)}>"
    j = _jsonable(o)
    return j[:500] + "…" if isinstance(j, str) and len(j) > 500 else j


def create_app(root: str | Path = ".") -> FastAPI:
    root = Path(root).expanduser().resolve()
    exports = root / "nuscope_exports"
    app = FastAPI(title="NUScope Studio", version=__version__)

    @app.middleware("http")
    async def revalidate(request, call_next):   # pick up a new Studio version without a hard reload
        resp = await call_next(request)
        if not request.url.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-cache"
        return resp
    items: dict[str, Item] = {}
    tables: dict[str, pd.DataFrame] = {}

    def inside(rel: str) -> Path:
        p = (root / rel).resolve()
        if p != root and root not in p.parents:
            raise HTTPException(403, "outside the data folder")
        return p

    def get(i: str) -> Item:
        if i not in items:
            raise HTTPException(404, "dataset not open")
        return items[i]

    def add(ds: Dataset, parent=None, op=None) -> Item:
        it = Item(uuid.uuid4().hex[:8], ds, parent, op)
        items[it.id] = it
        return it

    # ------------------------------------------------------------ library
    @app.get("/api/state")
    def state():
        from ..globus import _configured_client_id
        return {"root": str(root), "name": root.name, "version": __version__,
                "globus": {"configured": bool(_configured_client_id())}, "open": [summary_of(i)["name"] for i in items.values()]}

    @app.get("/api/library")
    def library(path: str = "", q: str = ""):
        base = inside(path)
        if not base.is_dir():
            raise HTTPException(404, "not a folder")
        entries = []
        if q:  # recursive search
            for p in sorted(base.rglob("*")):
                if len(entries) >= 400:
                    break
                if p.is_file() and p.suffix.lower() in DATA_EXT and q.lower() in p.name.lower() and "nuscope_exports" not in p.parts:
                    entries.append(p)
        else:
            entries = sorted(base.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        out = []
        for p in entries:
            if p.name.startswith(".") or p.name == "__pycache__":
                continue
            is_dir = p.is_dir() and p.suffix.lower() != ".zarr"
            if not is_dir and p.suffix.lower() not in DATA_EXT | {".zarr"}:
                continue
            st = p.stat()
            out.append({"name": p.name, "path": str(p.relative_to(root)), "dir": is_dir,
                        "size": None if is_dir else st.st_size, "mtime": st.st_mtime,
                        "ext": p.suffix.lower().lstrip("."),
                        "sidecar": (not is_dir) and any(p.with_suffix(s).exists() for s in (".txt", ".TXT"))})
        return {"path": str(base.relative_to(root)) if base != root else "", "entries": out}

    @app.post("/api/open")
    def open_(req: dict = Body(...)):
        src = req.get("url") or str(inside(req["path"]))
        already = [it for it in items.values() if it.source == src]
        if already:   # opening a file twice shows the open copy, with its results
            return [summary_of(it) for it in already]
        try:
            dss = load_all(src)
        except Exception as e:
            raise HTTPException(400, f"Could not open {Path(str(src)).name}: {e}")
        out = []
        for d in dss:
            it = add(d)
            it.source = src
            out.append(summary_of(it))
        return out

    @app.post("/api/upload")
    async def upload(files: list[UploadFile] = File(...)):
        dest = root / "uploads"
        dest.mkdir(exist_ok=True)
        saved = []
        for f in files:
            p = dest / Path(f.filename).name
            with open(p, "wb") as out:
                shutil.copyfileobj(f.file, out)
            saved.append(str(p.relative_to(root)))
        return {"saved": saved}

    @app.get("/api/session")
    def session():
        return [{k: v for k, v in summary_of(i).items() if k in ("id", "name", "parent", "op", "shape", "view", "signal")}
                for i in items.values()]

    @app.delete("/api/ds/{i}")
    def close(i: str):
        for k in [k for k, it in items.items() if k == i or it.parent == i]:
            items.pop(k, None)
        return {"closed": i}

    # ------------------------------------------------------------ dataset views
    @app.get("/api/ds/{i}")
    def ds_info(i: str):
        return JSONResponse(json.loads(json.dumps(summary_of(get(i)), default=str)))

    @app.get("/api/ds/{i}/original")
    def original(i: str):
        return JSONResponse(json.loads(json.dumps(_trim(get(i).ds.original_metadata), default=str)))

    @app.get("/api/ds/{i}/histogram")
    def histogram(i: str, frame: int = 0, bins: int = 256):
        img = image_of(get(i), frame)
        finite = img[np.isfinite(img)]
        lo, hi = np.percentile(finite, (0.5, 99.5)) if finite.size else (0.0, 1.0)
        mn, mx = float(finite.min()), float(finite.max())
        h, e = np.histogram(finite, bins=bins, range=(mn, mx if mx > mn else mn + 1))
        return {"counts": h.tolist(), "edges": e.tolist(), "auto": [float(lo), float(hi)], "min": mn, "max": mx}

    @app.get("/api/ds/{i}/image")
    def image(i: str, frame: int = 0, lo: Optional[float] = None, hi: Optional[float] = None,
              gamma: float = 1.0, log: bool = False):
        img = image_of(get(i), frame)
        if lo is None or hi is None:
            lo, hi = np.percentile(img[np.isfinite(img)], (0.5, 99.5))
        return Response(png(to_u8(img, lo, hi, gamma, log)), media_type="image/png",
                        headers={"Cache-Control": "no-store"})

    @app.get("/api/ds/{i}/value")
    def value(i: str, y: int, x: int, frame: int = 0):
        img = image_of(get(i), frame)
        y, x = int(np.clip(y, 0, img.shape[0] - 1)), int(np.clip(x, 0, img.shape[1] - 1))
        return {"y": y, "x": x, "value": float(img[y, x])}

    @app.get("/api/ds/{i}/pick")
    def pick(i: str, y: int, x: int):
        it = get(i)
        v = view_of(it.ds)
        a = it.ds.numpy()
        ia = v.get("image_axes", [])
        idx = [slice(None)] * a.ndim
        for ax, val in zip(ia, (y, x)):
            idx[ax] = int(np.clip(val, 0, a.shape[ax] - 1))
        sub = np.asarray(a[tuple(idx)], dtype=np.float64)
        if v["kind"] == "spectrum_image":
            ax = it.ds.axes[v["signal_axes"][0]]
            return {"kind": "spectrum", "x": ax.values().tolist(), "y": sub.tolist(), "units": ax.units, "name": ax.name}
        if v["kind"] == "4d":
            it.cache["pick"] = sub
            sig = [it.ds.axes[k] for k in v["signal_axes"]]
            return {"kind": "pattern", "shape": list(sub.shape), "units": sig[-1].units, "scale": sig[-1].scale}
        raise HTTPException(400, "pick works on spectrum images and 4D data")

    @app.get("/api/ds/{i}/pick.png")
    def pick_png(i: str):
        sub = get(i).cache.get("pick")
        if sub is None:
            raise HTTPException(404)
        lo, hi = np.percentile(sub, (0.5, 99.9))
        return Response(png(to_u8(sub, lo, hi, log=True)), media_type="image/png", headers={"Cache-Control": "no-store"})

    @app.get("/api/ds/{i}/spectrum")
    def spectrum(i: str):
        ds = get(i).ds
        a = ds.numpy().astype(np.float64)
        if ds.ndim != 1:
            raise HTTPException(400, "not a spectrum")
        return {"x": ds.axes[0].values().tolist(), "y": a.tolist(), "units": ds.axes[0].units, "name": ds.axes[0].name}

    # ------------------------------------------------------------ analysis
    @app.post("/api/ds/{i}/run")
    def run(i: str, req: dict = Body(...)):
        it = get(i)
        op, params = req.get("op"), dict(req.get("params") or {})
        if op not in OPS:
            raise HTTPException(400, f"unknown operation {op}")
        ds = it.ds
        v = view_of(ds)
        if ds.ndim != 2 and op not in ("stats",):
            img = image_of(it, int(req.get("frame", 0)))
            ds = ds.derive(img, axes=[ds.axes[k] for k in v.get("image_axes", [ds.ndim - 2, ds.ndim - 1])], signal="image")
            ds.provenance.record("studio.view", {"view": v["kind"], "frame": req.get("frame", 0)})
        for k in ("start", "end", "y", "x"):
            if k in params and isinstance(params[k], list):
                params[k] = tuple(params[k])
        t0 = time.time()
        try:
            out = OPS[op](ds, **params)
        except Exception as e:
            raise HTTPException(400, f"{op} failed: {e}")
        dt = round(time.time() - t0, 2)
        if isinstance(out, Dataset):
            out.name = f"{op} · {it.ds.name}"
            new = add(out, parent=i, op=op)
            return {"kind": "dataset", "seconds": dt, "dataset": summary_of(new)}
        if isinstance(out, pd.DataFrame):
            tid = uuid.uuid4().hex[:8]
            labels = out.attrs.pop("labels", None)
            prov = out.attrs.pop("provenance", None)
            tables[tid] = out
            if labels is not None:
                it.cache[("overlay", tid)] = labels
            cols = list(map(str, out.columns))
            return {"kind": "table", "seconds": dt, "table": tid, "columns": cols,
                    "rows": json.loads(out.head(5000).to_json(orient="values")),
                    "n": len(out), "attrs": _jsonable({k: v for k, v in out.attrs.items() if k != "labels"}),
                    "overlay": labels is not None,
                    "activity": vars(prov.activities[-1]) if prov else None}
        if isinstance(out, dict):
            prov = out.pop("provenance", None)
            return {"kind": "values", "seconds": dt, "values": _jsonable(out),
                    "activity": vars(prov.activities[-1]) if prov else None}
        return {"kind": "none"}

    @app.get("/api/ds/{i}/overlay/{tid}.png")
    def overlay(i: str, tid: str):
        lab = get(i).cache.get(("overlay", tid))
        if lab is None:
            raise HTTPException(404)
        from skimage.segmentation import find_boundaries
        b = find_boundaries(lab, mode="inner")
        rgba = np.zeros(lab.shape + (4,), np.uint8)
        rgba[b] = (255, 196, 0, 255)
        return Response(png(rgba), media_type="image/png", headers={"Cache-Control": "no-store"})

    @app.get("/api/table/{tid}.csv")
    def table_csv(tid: str):
        if tid not in tables:
            raise HTTPException(404)
        return Response(tables[tid].to_csv(index=False), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="nuscope_{tid}.csv"'})

    # ------------------------------------------------------------ saving and export
    def _safe(name: str) -> str:
        return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)[:80] or "dataset"

    @app.post("/api/ds/{i}/save")
    def save_ds(i: str, req: dict = Body(...)):
        it = get(i)
        fmt = req.get("format", "nxs")
        if fmt not in ("nxs", "tif", "zarr"):
            raise HTTPException(400, "format is nxs, tif or zarr")
        exports.mkdir(exist_ok=True)
        p = exports / f"{_safe(it.ds.name)}.{fmt}"
        save(it.ds, p, overwrite=True)
        return {"path": str(p.relative_to(root)), "download": None if fmt == "zarr" else f"/api/file?path={p.relative_to(root)}"}

    @app.get("/api/ds/{i}/figure")
    def figure(i: str, fmt: str = "png", frame: int = 0, lo: Optional[float] = None, hi: Optional[float] = None,
               gamma: float = 1.0, log: bool = False, cmap: str = "gray", scalebar: bool = True, colorbar: bool = False,
               dpi: int = 300):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import LinearSegmentedColormap
        it = get(i)
        img = image_of(it, frame)
        if lo is None or hi is None:
            lo, hi = np.percentile(img, (0.5, 99.5))
        u = to_u8(img, lo, hi, gamma, log) / 255.0
        cm = LinearSegmentedColormap.from_list("nu", ["#000000", "#4E2A84", "#B6ACD1", "#FFFFFF"]) if cmap == "purple" else cmap
        h, w = u.shape
        fig = plt.figure(figsize=(6 * w / max(h, w) + (1.0 if colorbar else 0), 6 * h / max(h, w)))
        ax = fig.add_axes([0, 0, 0.86 if colorbar else 1, 1])
        im = ax.imshow(u, cmap=cm, vmin=0, vmax=1, interpolation="nearest")
        ax.set_axis_off()
        ds = it.ds
        axes = [ds.axes[k] for k in view_of(ds).get("image_axes", [0, 1])]
        ps = axes[-1].scale_nm()
        if scalebar and ps:
            target = w * ps / 5
            nice = min((v for v in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1e3, 2e3, 5e3, 1e4, 2e4, 5e4, 1e5, 2e5, 5e5)
                        if v >= target * 0.6), default=target)
            px = nice / ps
            ax.add_patch(plt.Rectangle((w * 0.96 - px, h * 0.93), px, h * 0.012, color="white"))
            ax.text(w * 0.96 - px / 2, h * 0.915, f"{nice / 1e3:g} µm" if nice >= 1e3 else f"{nice:g} nm",
                    color="white", ha="center", va="bottom", fontsize=11, fontweight="bold")
        if colorbar:
            cax = fig.add_axes([0.88, 0.1, 0.03, 0.8])
            cb = fig.colorbar(im, cax=cax)
            cb.set_ticks([0, 1])
            cb.set_ticklabels([f"{lo:.4g}", f"{hi:.4g}"])
        buf = io.BytesIO()
        fig.savefig(buf, format={"tif": "tiff"}.get(fmt, fmt), dpi=dpi, bbox_inches="tight", pad_inches=0)
        plt.close(fig)
        mt = {"png": "image/png", "pdf": "application/pdf", "tif": "image/tiff", "svg": "image/svg+xml"}.get(fmt, "application/octet-stream")
        return Response(buf.getvalue(), media_type=mt,
                        headers={"Content-Disposition": f'attachment; filename="{_safe(ds.name)}.{fmt}"'})

    @app.get("/api/ds/{i}/prov.json")
    def prov_json(i: str):
        ds = get(i).ds
        return Response(json.dumps(ds.provenance.to_prov_json(), indent=2, default=str), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{_safe(ds.name)}.prov.json"'})

    @app.post("/api/crate")
    def crate(req: dict = Body(...)):
        from ..crate import write_crate
        dss = [get(i).ds for i in req.get("ids", [])]
        if not dss:
            raise HTTPException(400, "choose at least one dataset")
        folder = exports / f"crate_{time.strftime('%Y%m%d_%H%M%S')}"
        write_crate(dss, folder, title=req.get("title") or "NUScope datasets", description=req.get("description", ""),
                    authors=[a for a in req.get("authors", []) if a.get("name")])
        archive = shutil.make_archive(str(folder), "zip", folder)
        rel = Path(archive).relative_to(root)
        return {"folder": str(folder.relative_to(root)), "download": f"/api/file?path={rel}"}

    @app.get("/api/file")
    def file(path: str):
        p = inside(path)
        if not p.is_file():
            raise HTTPException(404)
        return FileResponse(p, filename=p.name)

    # ------------------------------------------------------------ Globus
    @app.get("/api/globus/ls")
    def globus_ls(collection: str, path: str = "/"):
        from ..globus import GlobusError, session
        try:
            files = session().ls(collection, path)
        except GlobusError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(400, f"Globus: {e}. If you are not logged in, run: nuscope globus login {collection}")
        return {"collection": collection, "path": path,
                "entries": [{"name": f.name, "path": f.path, "dir": f.type == "dir", "size": f.size,
                             "mtime": f.last_modified, "ext": Path(f.name).suffix.lower().lstrip(".")} for f in files
                            if f.type == "dir" or Path(f.name).suffix.lower() in DATA_EXT]}

    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
    return app


def serve(root: str | Path = ".", host: str = "127.0.0.1", port: int = 8770, open_browser: bool = False):
    import uvicorn
    url = f"http://{host}:{port}"
    print(f"NUScope Studio → {url}   (data folder: {Path(root).expanduser().resolve()})")
    if open_browser:
        import threading
        import webbrowser
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(root), host=host, port=port, log_level="warning")


__all__ = ["create_app", "serve", "view_of"]
