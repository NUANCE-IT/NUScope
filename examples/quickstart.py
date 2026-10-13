"""NUScope quick start: load, inspect, analyze, save, trace.

    python examples/quickstart.py <image file | globus://collection/path>
"""
import sys

import nuscope as ns
from nuscope import analyze as an

img = ns.load(sys.argv[1])
print(img.describe(), "\n")
print("noise and SNR:", {k: round(v, 3) for k, v in an.stats(img).items() if k != "provenance"})
if img.ndim == 2:
    clean = an.denoise(img, method="nlm")
    parts = an.particles(clean)
    print(f"{len(parts)} particles, median equivalent diameter {parts.eq_diameter_nm.median():.1f} "
          f"{parts.attrs['units']}")
    out = ns.save(clean, img.name + ".nxs", overwrite=True)
    print("saved", out)
    print("\nprovenance:\n" + "\n".join(ns.load(out).provenance.lineage()))
