"""Calibrated analysis of electron-microscopy images.

Every function takes a :class:`~nuscope.Dataset` and returns a new dataset or a
table (pandas DataFrame) whose provenance records the operation, its
parameters, the input it used and the software versions. Physical units
follow the dataset's calibration (nm, nm², 1/nm).
"""
from .core import tracked  # noqa: F401
from .basic import (bin_image, calibrate, crop, denoise, fft, line_profile,  # noqa: F401
                    radial_profile, stats, subtract_background)
from .particles import particles, threshold  # noqa: F401

__all__ = ["tracked", "stats", "crop", "bin_image", "calibrate", "denoise", "subtract_background", "fft",
           "radial_profile", "line_profile", "threshold", "particles"]
