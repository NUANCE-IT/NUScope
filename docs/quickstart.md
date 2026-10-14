# Quickstart

## Open a file

```python
import nuscope as ns

ds = ns.load("S-3400/FS-Ti_Sample_11-BSE.tif")
print(ds)               # <Dataset 'FS-Ti_Sample_11-BSE' image (448, 640) uint8 396.875 nm/px>
print(ds.describe())    # instrument, voltage, magnification, working distance, detector ...
ds.metadata["beam"]     # {'voltage_kV': 30.0, 'emission_current_uA': 122.0}
ds.axes                 # calibrated axes: name, size, scale, units
```

Files with several datasets (an EMD with a HAADF image and an EDS cube, for example) give a list with
`ns.load_all(path)`.

## Analyze

```python
from nuscope import analyze as an

an.stats(ds)                                   # mean, std, noise sigma, SNR
clean = an.denoise(ds, method="nlm")           # new Dataset; history extended
table = an.particles(clean, min_area_nm2=500)  # pandas DataFrame in nm and nm²
spectrum = an.fft(ds)                          # axes in 1/nm
profile = an.radial_profile(spectrum)          # periodicities
```

## Save, verify, share

```python
ns.save(clean, "clean.h5")             # HDF5 (NeXus layout) with metadata, history and a seal
print(ns.verify("clean.h5"))           # SIGNED AND INTACT ... / CHANGED AFTER SEALING ...
print("\n".join(clean.provenance.lineage()))
```

```python
from nuscope.crate import write_crate
write_crate([clean], "deposit", title="Ti alloy BSE", authors=[{"name": "Your Name", "orcid": "https://orcid.org/..."}])
```

## Command line and Studio

```bash
nuscope info sample.dm4
nuscope convert sample.tif sample.h5
nuscope verify sample.h5
nuscope studio /path/to/data --open
```
