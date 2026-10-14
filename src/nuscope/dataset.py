"""The NUScope dataset: an array with calibrated axes, normalized metadata,
the original vendor metadata, and its provenance."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Optional

import numpy as np

from . import metadata as md
from .provenance import Provenance


@dataclass
class Axis:
    name: str                  # "y", "x", "z", "energy", "kx", ...
    size: int
    scale: float = 1.0
    units: str = "px"
    offset: float = 0.0
    navigate: bool = False     # True for scan/navigation axes of spectrum images

    def values(self) -> np.ndarray:
        return self.offset + self.scale * np.arange(self.size)

    def scale_nm(self) -> Optional[float]:
        return md.to_nm(self.scale, self.units)


@dataclass
class Dataset:
    data: Any                                   # numpy or dask array
    axes: list[Axis]
    metadata: dict = field(default_factory=md.empty)
    original_metadata: dict = field(default_factory=dict)
    provenance: Provenance = field(default_factory=Provenance)
    name: str = ""
    signal: str = "image"                       # image | spectrum | spectrum_image | diffraction | stack
    integrity: Any = field(default=None, repr=False, compare=False)   # integrity.Report when read from a NUScope file

    def __post_init__(self):
        if len(self.axes) != np.ndim(self.data):
            raise ValueError(f"{len(self.axes)} axes for a {np.ndim(self.data)}-D array")
        for a, n in zip(self.axes, np.shape(self.data)):
            if a.size != n:
                a.size = int(n)

    # ------------------------------------------------------------ convenience
    @classmethod
    def from_array(cls, data, pixel_size_nm: Optional[float | tuple] = None, name: str = "", **meta) -> "Dataset":
        data = np.asarray(data)
        names = ["z", "y", "x"][-data.ndim:] if data.ndim <= 3 else [f"axis{i}" for i in range(data.ndim)]
        ps = pixel_size_nm if isinstance(pixel_size_nm, (tuple, list)) else [pixel_size_nm] * data.ndim
        axes = [Axis(n, s, scale=p if p else 1.0, units="nm" if p else "px") for n, s, p in zip(names, data.shape, ps)]
        ds = cls(data, axes, metadata=md.merge(md.empty(), meta), name=name)
        eid = ds.provenance.add_array(data, label=name or "array")
        ds.provenance.record("create.from_array", {"pixel_size_nm": pixel_size_nm}, generated=[eid])
        return ds

    @property
    def shape(self) -> tuple:
        return tuple(np.shape(self.data))

    @property
    def ndim(self) -> int:
        return len(self.shape)

    @property
    def dtype(self):
        return self.data.dtype

    @property
    def pixel_size_nm(self) -> Optional[float]:
        """Pixel size of the last (x) axis in nm, or None when uncalibrated."""
        spatial = [a for a in self.axes if a.scale_nm() is not None]
        return spatial[-1].scale_nm() if spatial else None

    @property
    def calibrated(self) -> bool:
        return self.pixel_size_nm is not None

    def numpy(self) -> np.ndarray:
        d = self.data
        return np.asarray(d.compute() if hasattr(d, "compute") else d)

    def derive(self, data, *, axes: Optional[list[Axis]] = None, name: Optional[str] = None,
               signal: Optional[str] = None, **meta_updates) -> "Dataset":
        """New dataset sharing metadata and a copy of the provenance."""
        out = Dataset(data, [replace(a) for a in (axes or self.axes)],
                      metadata=md.merge(self.metadata, meta_updates), original_metadata=self.original_metadata,
                      provenance=self.provenance.copy(), name=name or self.name, signal=signal or self.signal)
        return out

    def describe(self) -> str:
        cal = " × ".join(f"{a.size} {a.name} @ {a.scale:g} {a.units}" for a in self.axes)
        lines = [f"{self.name or 'dataset'} · {self.signal} · {self.dtype} · {cal}"]
        lines += ["  " + s for s in md.summary(self.metadata)]
        if self.provenance.activities:
            src = ", ".join(e.label or e.location or e.id for e in self.provenance.sources()) or "-"
            lines.append(f"  history: {len(self.provenance.activities)} step(s); source {src}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        last = self.axes[-1] if self.axes else None
        cal = (f"{self.pixel_size_nm:g} nm/px" if self.calibrated else
               f"{last.scale:g} {last.units}/px" if last and last.units != "px" else "uncalibrated")
        return f"<Dataset {self.name!r} {self.signal} {self.shape} {self.dtype} {cal}>"

    def plot(self, ax=None, cmap: str = "gray", scalebar: bool = True, **kw):
        """Quick look with a calibrated scale bar (needs matplotlib)."""
        import matplotlib.pyplot as plt
        img = self.numpy()
        while img.ndim > 2:
            img = img[img.shape[0] // 2]
        ax = ax or plt.gca()
        ax.imshow(img, cmap=cmap, **kw)
        ax.set_axis_off()
        ps = self.pixel_size_nm
        if scalebar and ps:
            target = img.shape[1] * ps / 5
            nice = min((v for v in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1e3, 2e3, 5e3, 1e4, 2e4, 5e4, 1e5)
                        if v >= target * 0.6), default=target)
            px = nice / ps
            h, w = img.shape
            ax.plot([w * 0.95 - px, w * 0.95], [h * 0.93, h * 0.93], color="white", lw=3)
            ax.text(w * 0.95 - px / 2, h * 0.9, f"{nice / 1e3:g} µm" if nice >= 1e3 else f"{nice:g} nm",
                    color="white", ha="center", va="bottom", fontsize=9)
        ax.set_title(self.name, fontsize=9)
        return ax


__all__ = ["Dataset", "Axis"]
