"""NUScope: read, analyze, save and trace electron-microscopy data at the
NUANCE Center, Northwestern University.

    import nuscope as ns
    img = ns.load("Quanta/ResolutionTest_SE_10kx_5kv_008.tif")        # or globus://<collection>/<path>
    print(img.describe())
    parts = ns.analyze.particles(ns.analyze.denoise(img))
    ns.save(img, "result.h5")                                        # metadata + provenance + seal inside
    print(ns.verify("result.h5"))                                    # intact? signed by whom?
    print("\\n".join(img.provenance.lineage()))

Created by Roberto dos Reis (@rmsreis), NUANCE Center. Original instrument
loaders by Nathaniel Kabat.
"""
__version__ = "0.3.0"

from .dataset import Axis, Dataset  # noqa: E402,F401
from .io import formats, load, load_all, save  # noqa: E402,F401
from .provenance import Provenance  # noqa: E402,F401
from . import analyze, integrity, metadata  # noqa: E402,F401
from .integrity import verify  # noqa: E402,F401

__all__ = ["Dataset", "Axis", "Provenance", "load", "load_all", "save", "verify", "formats", "analyze", "integrity",
           "metadata", "__version__"]
