# Analysis

Every function works in physical units and records itself in the dataset's history (operation, parameters,
input and output content hashes, software versions, person, time).

```python
from nuscope import analyze as an
```

| Function | Returns | Notes |
|---|---|---|
| `stats(ds)` | dict | mean, std, min, max, 1st/99th percentiles, noise σ (wavelet estimate), SNR |
| `crop(ds, y=(y0, y1), x=(x0, x1))` | Dataset | |
| `bin_image(ds, factor=2)` | Dataset | pixel size scales with the factor |
| `calibrate(ds, pixel_size_nm, reason="")` | Dataset | the reason (e.g. a calibration standard) is kept in the history |
| `denoise(ds, method="nlm", strength=1.0)` | Dataset | `nlm` (non-local means), `gaussian`, `median` |
| `subtract_background(ds, sigma_nm=None, sigma_px=50)` | Dataset | removes slow shading |
| `fft(ds, window=True, log=True)` | Dataset | power spectrum with axes in 1/nm |
| `radial_profile(ds, bins=200)` | DataFrame | azimuthal average: `q` (1/nm), `intensity`, `pixels`, `period` (nm) |
| `line_profile(ds, start, end, width=1)` | DataFrame | distance in nm along the line |
| `threshold(ds, method="otsu", value=None, dark=False)` | Dataset (mask) | |
| `particles(ds, method="otsu", min_area_nm2=0, exclude_border=True, separate=False)` | DataFrame | area, equivalent diameter, Feret, aspect ratio, circularity, orientation, mean intensity, in nm |

```python
table = an.particles(an.denoise(ds), min_area_nm2=500, separate=True)
table.attrs["area_fraction"]        # fraction of the field covered
table["eq_diameter_nm"].median()
```

Your own functions can join the history with the `tracked` decorator:

```python
from nuscope.analyze.core import tracked

@tracked("my_lab.flatten")
def flatten(ds, order=2):
    ...
    return ds.derive(new_array)
```
