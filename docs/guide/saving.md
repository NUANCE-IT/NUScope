# Saving and sharing

```python
ns.save(ds, "result.h5")       # HDF5, NeXus layout
ns.save(ds, "result.nxs")      # the same, with the NeXus extension
ns.save(ds, "result.zarr")     # Zarr v3, for very large data
ns.save(ds, "result.tif")      # TIFF, calibrated, NUScope document in the description
```

Every format carries the data, calibrated axes, the normalized and original metadata, the full history and a
[seal](integrity.md), and every one of them opens again with `ns.load()` exactly as it was saved. Saving adds
a step to the history, and missing folders are created.

| Format | Best for | Notes |
|---|---|---|
| `.h5` / `.nxs` | most data; sharing with h5py, HDFView, MATLAB, NeXus tools | gzip-compressed; summary of the seal in the root attributes |
| `.zarr` | very large data, cloud storage | chunked |
| `.tif` | image viewers, ImageJ/Fiji | resolution tags carry the pixel size |

`ns.save(..., sign=False)` seals without signing; `sign=True` refuses to save if you have no key. The
default signs when you have a key.

## RO-Crate packages for a repository

```python
from nuscope.crate import write_crate
write_crate([a, b], "deposit", title="Ti alloy BSE series",
            description="...", authors=[{"name": "Your Name", "orcid": "https://orcid.org/..."}],
            include_sources=True)
```

```bash
nuscope crate deposit/ a.h5 b.h5 --title "Ti alloy BSE series" --author "Your Name|https://orcid.org/..."
```

The folder holds the datasets and an `ro-crate-metadata.json` (RO-Crate 1.1) describing files, people,
instruments, the facility, every processing step, and each file's seal and signers. Zip it and upload it
to a repository that issues a DOI.

## PROV-JSON

```python
import json
json.dump(ds.provenance.to_prov_json(), open("prov.json", "w"))
```

or `nuscope provenance result.h5 --prov-json prov.json`.
