# NUScope

**Read, analyze, save and trace electron-microscopy data at the NUANCE Center, Northwestern University.**

Created by **Roberto dos Reis ([@rmsreis](https://github.com/rmsreis))** · NUANCE Center, Northwestern University

NUScope is the data layer of the NUScope program. One `load()` opens any NUANCE microscope file, locally or
straight from a Globus collection, and returns calibrated data with one metadata schema for every instrument.
Every step after that (analysis, saving, sharing) is recorded as provenance that travels inside the files it
writes. Those files are sealed with SHA-256 hashes and signed with your ORCID-linked key, so anyone can check
that data, calibration, metadata and history are exactly as you left them.

```python
import nuscope as ns
from nuscope import analyze as an

img = ns.load("Quanta/ResolutionTest_SE_10kx_5kv_008.tif")   # or "globus://<collection-id>/path/file.dm4"
print(img.describe())                                        # instrument, kV, magnification, WD, detector ...
parts = an.particles(an.denoise(img), min_area_nm2=500)       # sizes in nm, with their own provenance
ns.save(img, "result.h5")                                    # HDF5 with metadata, provenance and a seal
print(ns.verify("result.h5"))                                # intact? signed by whom?
```

<div class="grid cards" markdown>

- :material-file-search: **[Read](guide/reading.md)**

    Thermo Fisher / FEI, Zeiss, Hitachi and JEOL SEM/FIB images natively; Gatan DM3/DM4, Velox EMD,
    TIA, Bruker, EDAX, MRC and 30 more through RosettaSciIO.

- :material-tune: **[One metadata schema](guide/metadata.md)**

    Instrument, beam, optics, detector, acquisition and sample, the same for every vendor.
    The vendor's own metadata is kept untouched.

- :material-chart-bell-curve: **[Analyze in physical units](guide/analysis.md)**

    Noise, denoising, background, FFT and radial profiles, line profiles, particles: in nm, nm² and 1/nm.

- :material-shield-check: **[Tamper-evident provenance](guide/integrity.md)**

    A hash-chained history, a seal in every file, and Ed25519 signatures tied to your ORCID iD.

- :material-application: **[NUScope Studio](guide/studio.md)**

    A browser application for the whole workflow: view, measure, analyze, save, sign and package.

- :material-cloud-sync: **[Globus](guide/globus.md)** and **[NUANCE-MCP](guide/nuance-mcp.md)**

    Read straight from Globus collections. Let an LLM driving a microscope through NUANCE-MCP save
    every acquisition as a sealed, signed file.

</div>

## The NUScope family

| Package | What it does |
|---|---|
| **NUScope** (this package) | Reading, metadata, analysis, saving, provenance, integrity, Studio, Globus |
| [NUScope-TOMO](https://github.com/NUANCE-IT/NUScope-TOMO) | FIB-SEM slice-and-view tomography; plugs in as `nuscope tomo` |
| [EMDataBridge](https://github.com/NUANCE-IT/EMDataBridge) | Format standardization and the shared researcher identity (ORCID, signing keys) |
| [NUANCE-MCP](https://github.com/NUANCE-IT/NUANCE-MCP) | Model Context Protocol server for microscope control; loads NUScope and NUScope-TOMO as plugins |
