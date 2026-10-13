"""Particle / feature analysis in physical units."""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from scipy import ndimage as ndi

from ..dataset import Dataset
from .core import tracked


@tracked("analyze.threshold")
def threshold(ds: Dataset, method: str = "otsu", value: Optional[float] = None, dark: bool = False) -> Dataset:
    """Binary mask: features brighter (or darker, ``dark=True``) than the threshold."""
    from skimage import filters
    a = ds.numpy().astype(np.float64)
    t = value if value is not None else {"otsu": filters.threshold_otsu, "li": filters.threshold_li,
                                         "triangle": filters.threshold_triangle}[method](a)
    m = a < t if dark else a > t
    out = ds.derive(m.astype(np.uint8), signal="mask")
    out.metadata = dict(out.metadata, analysis={"threshold": float(t), "method": method if value is None else "value"})
    return out


@tracked("analyze.particles")
def particles(ds: Dataset, method: str = "otsu", dark: bool = False, min_area_nm2: float = 0.0,
              exclude_border: bool = True, separate: bool = False, min_distance_nm: Optional[float] = None) -> pd.DataFrame:
    """One row per particle: area, equivalent diameter, Feret, aspect ratio, circularity,
    orientation and mean intensity, in nm. Accepts an image (thresholded with ``method``)
    or a mask; ``separate`` splits touching particles with a distance-transform watershed."""
    from skimage import filters, measure, segmentation
    a = ds.numpy()
    if a.ndim != 2:
        raise ValueError("expects a 2-D image")
    if ds.signal == "mask" or a.dtype == bool or set(np.unique(a)) <= {0, 1}:
        m = a.astype(bool)
    else:
        f = a.astype(np.float64)
        t = {"otsu": filters.threshold_otsu, "li": filters.threshold_li, "triangle": filters.threshold_triangle}[method](f)
        m = f < t if dark else f > t
    m = ndi.binary_opening(m, iterations=1)
    m = ndi.binary_fill_holes(m)
    ps = ds.pixel_size_nm or 1.0
    if separate:
        dist = ndi.distance_transform_edt(m) * ps
        md_px = max(1, int((min_distance_nm or 10 * ps) / ps))
        from skimage.feature import peak_local_max
        pk = peak_local_max(dist, min_distance=md_px, labels=ndi.label(m)[0], exclude_border=False)
        markers = np.zeros(m.shape, np.int32)
        markers[tuple(pk.T)] = np.arange(1, len(pk) + 1)
        lab = segmentation.watershed(-dist, markers, mask=m)
    else:
        lab = measure.label(m)
    if exclude_border:
        lab = segmentation.clear_border(lab)
    intensity = a.astype(np.float64)
    rows = []
    for r in measure.regionprops(lab, intensity_image=intensity):
        area = r.area * ps * ps
        if area < min_area_nm2:
            continue
        per = r.perimeter * ps
        rows.append({"label": r.label, "area_nm2": area, "eq_diameter_nm": r.equivalent_diameter_area * ps,
                     "feret_max_nm": r.feret_diameter_max * ps, "major_nm": r.axis_major_length * ps,
                     "minor_nm": r.axis_minor_length * ps,
                     "aspect_ratio": r.axis_major_length / r.axis_minor_length if r.axis_minor_length else np.inf,
                     "circularity": 4 * np.pi * area / per ** 2 if per else np.nan, "solidity": r.solidity,
                     "orientation_deg": np.degrees(r.orientation), "mean_intensity": r.intensity_mean,
                     "centroid_y_nm": r.centroid[0] * ps, "centroid_x_nm": r.centroid[1] * ps})
    df = pd.DataFrame(rows)
    kept = np.isin(lab, df["label"].to_numpy()) if len(df) else np.zeros(lab.shape, bool)
    df.attrs["labels"] = np.where(kept, lab, 0).astype(np.int32)   # for overlays (Studio)
    df.attrs["units"] = "nm" if ds.pixel_size_nm else "px"
    df.attrs["area_fraction"] = float(m.mean())
    return df


__all__ = ["threshold", "particles"]
