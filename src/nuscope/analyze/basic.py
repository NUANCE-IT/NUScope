"""Basic calibrated image operations."""
from __future__ import annotations

from dataclasses import replace
from typing import Optional

import numpy as np
import pandas as pd
from scipy import ndimage as ndi

from ..dataset import Axis, Dataset
from .core import tracked


def _img(ds: Dataset) -> np.ndarray:
    a = ds.numpy()
    if a.ndim != 2:
        raise ValueError(f"expects a 2-D image, got shape {a.shape}")
    return a


@tracked("analyze.stats")
def stats(ds: Dataset) -> dict:
    """Intensity statistics and an estimate of the noise (Gaussian sigma) and SNR."""
    from skimage.restoration import estimate_sigma
    a = ds.numpy().astype(np.float64)
    lo, hi = np.percentile(a, (1, 99))
    sig = float(estimate_sigma(a if a.ndim == 2 else a[a.shape[0] // 2]))
    return {"mean": float(a.mean()), "std": float(a.std()), "min": float(a.min()), "max": float(a.max()),
            "p1": float(lo), "p99": float(hi), "noise_sigma": sig, "snr": float((hi - lo) / sig) if sig else np.inf}


@tracked("analyze.crop")
def crop(ds: Dataset, y: tuple[int, int], x: tuple[int, int]) -> Dataset:
    a = ds.numpy()[..., y[0]:y[1], x[0]:x[1]]
    axes = [replace(ax) for ax in ds.axes]
    axes[-2] = replace(axes[-2], size=a.shape[-2], offset=axes[-2].offset + y[0] * axes[-2].scale)
    axes[-1] = replace(axes[-1], size=a.shape[-1], offset=axes[-1].offset + x[0] * axes[-1].scale)
    return ds.derive(a, axes=axes)


@tracked("analyze.bin")
def bin_image(ds: Dataset, factor: int = 2) -> Dataset:
    a = _img(ds).astype(np.float32)
    h, w = a.shape[0] // factor * factor, a.shape[1] // factor * factor
    b = a[:h, :w].reshape(h // factor, factor, w // factor, factor).mean((1, 3))
    axes = [replace(ax, size=n, scale=ax.scale * factor) for ax, n in zip(ds.axes, b.shape)]
    return ds.derive(b, axes=axes)


@tracked("analyze.calibrate")
def calibrate(ds: Dataset, pixel_size_nm: float, reason: str = "") -> Dataset:
    """Set or correct the pixel size (e.g. from a calibration standard); the reason is kept."""
    axes = [replace(ax, scale=pixel_size_nm, units="nm") if ax.name in ("x", "y") else replace(ax) for ax in ds.axes]
    return ds.derive(ds.data, axes=axes)


@tracked("analyze.denoise")
def denoise(ds: Dataset, method: str = "nlm", strength: float = 1.0) -> Dataset:
    """'nlm' (non-local means), 'gaussian' or 'median'."""
    a = _img(ds).astype(np.float32)
    if method == "nlm":
        from skimage.restoration import denoise_nl_means, estimate_sigma
        lo, hi = float(a.min()), float(a.max())
        u = (a - lo) / (hi - lo or 1)
        s = float(estimate_sigma(u))
        out = denoise_nl_means(u, h=0.8 * strength * s, sigma=s, patch_size=5, patch_distance=6, fast_mode=True) * (hi - lo) + lo
    elif method == "gaussian":
        out = ndi.gaussian_filter(a, strength)
    elif method == "median":
        out = ndi.median_filter(a, size=max(3, int(2 * strength + 1)))
    else:
        raise ValueError("method is 'nlm', 'gaussian' or 'median'")
    return ds.derive(out.astype(np.float32))


@tracked("analyze.subtract_background")
def subtract_background(ds: Dataset, sigma_nm: Optional[float] = None, sigma_px: float = 50.0) -> Dataset:
    """Remove slow shading by subtracting a wide Gaussian blur."""
    a = _img(ds).astype(np.float32)
    s = sigma_nm / ds.pixel_size_nm if (sigma_nm and ds.pixel_size_nm) else sigma_px
    return ds.derive(a - ndi.gaussian_filter(a, s) + a.mean())


@tracked("analyze.fft")
def fft(ds: Dataset, window: bool = True, log: bool = True) -> Dataset:
    """Power spectrum with reciprocal-space axes in 1/nm (1/px when uncalibrated)."""
    a = _img(ds).astype(np.float64)
    a = a - a.mean()
    if window:
        a = a * np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1]))
    p = np.abs(np.fft.fftshift(np.fft.fft2(a))) ** 2
    out = np.log1p(p) if log else p
    axes = []
    for ax, n in zip(ds.axes, out.shape):
        d = ax.scale_nm() or 1.0
        unit = "1/nm" if ax.scale_nm() else "1/px"
        axes.append(Axis(f"k{ax.name}", n, scale=1.0 / (n * d), units=unit, offset=-(n // 2) / (n * d)))
    return ds.derive(out.astype(np.float32), axes=axes, signal="diffraction")


@tracked("analyze.radial_profile")
def radial_profile(ds: Dataset, bins: int = 200) -> pd.DataFrame:
    """Azimuthal average around the centre; on a power spectrum, peaks give lattice or feature periodicities."""
    a = _img(ds).astype(np.float64)
    ky = ds.axes[-2].values()[:, None]
    kx = ds.axes[-1].values()[None, :]
    r = np.hypot(ky, kx)
    edges = np.linspace(0, r.max(), bins + 1)
    idx = np.clip(np.digitize(r.ravel(), edges) - 1, 0, bins - 1)
    s = np.bincount(idx, a.ravel(), bins)
    n = np.bincount(idx, minlength=bins)
    q = 0.5 * (edges[1:] + edges[:-1])
    df = pd.DataFrame({"q": q, "intensity": s / np.maximum(n, 1), "pixels": n})
    df["period"] = np.where(q > 0, 1 / np.maximum(q, 1e-12), np.inf)
    df.attrs["units"] = {"q": ds.axes[-1].units, "period": ds.axes[-1].units.replace("1/", "")}
    return df[n > 0].reset_index(drop=True)


@tracked("analyze.line_profile")
def line_profile(ds: Dataset, start: tuple[float, float], end: tuple[float, float], width: int = 1) -> pd.DataFrame:
    """Intensity along a line between (y, x) pixel positions, averaged over ``width`` pixels."""
    from skimage.measure import profile_line
    a = _img(ds).astype(np.float64)
    prof = profile_line(a, start, end, linewidth=width, mode="reflect", reduce_func=np.mean)
    ps = ds.pixel_size_nm or 1.0
    length = np.hypot(end[0] - start[0], end[1] - start[1]) * ps
    return pd.DataFrame({"distance": np.linspace(0, length, len(prof)), "intensity": prof})


__all__ = ["stats", "crop", "bin_image", "calibrate", "denoise", "subtract_background", "fft", "radial_profile",
           "line_profile"]
