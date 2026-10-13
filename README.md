# NUScope

**Read, analyze, save and trace electron-microscopy data at the NUANCE Center, Northwestern University.**

Created by **Roberto dos Reis ([@rmsreis](https://github.com/rmsreis))** · NUANCE Center, Northwestern University ·
[NUANCE-IT/NUScope](https://github.com/NUANCE-IT/NUScope)

NUScope is the data layer of the NUScope program. One `load()` opens any NUANCE microscope file, locally or
straight from a Globus collection, and returns calibrated data with one metadata schema for every instrument.
Every step after that (analysis, saving, sharing) is recorded as provenance that travels inside the files it
writes. Domain modules build on it; [NUScope-TOMO](https://github.com/NUANCE-IT/NUScope-TOMO) (FIB-SEM tomography)
plugs in as `nuscope tomo`.

```python
import nuscope as ns
from nuscope import analyze as an

img = ns.load("Quanta/ResolutionTest_SE_10kx_5kv_008.tif")       # or "globus://<collection-id>/path/file.dm4"
print(img.describe())                                            # instrument, kV, mag, WD, detector, dwell, ...
parts = an.particles(an.denoise(img), min_area_nm2=500)           # table in nm, nm², with its own provenance
ns.save(img, "result.nxs")                                       # NeXus/HDF5 with metadata + provenance inside
print("\n".join(img.provenance.lineage()))
```

| | |
|---|---|
| **Read** | Thermo Fisher / FEI (Quanta, Helios, Scios, Nova, Apreo; data bar removed), Zeiss, Hitachi (S-4800, SU8030, S-3400) and JEOL (JSM-7900F) SEM/FIB images with their sidecar files, read natively. Through [RosettaSciIO](https://hyperspy.org/rosettasciio/): Gatan DM3/DM4 (with Microscope Info, DigiScan, EELS tags mapped), Thermo Fisher Velox EMD, TIA SER/EMI, JEOL, Bruker BCF, EDAX, MRC, MIB and 30 more |
| **One metadata schema** | `instrument`, `technique`, `beam` (kV, nA), `optics` (magnification, WD, camera length, HFW), `detector`, `acquisition` (date, dwell, integration, operator), `sample` (name, stage), `facility`. The vendor's own block is kept untouched in `original_metadata` |
| **Analyze** | `stats` (noise, SNR), `crop`, `bin_image`, `calibrate` (with a reason, e.g. a standard), `denoise`, `subtract_background`, `fft` (axes in 1/nm), `radial_profile` (periodicities), `line_profile` (nm), `threshold`, `particles` (area, equivalent diameter, Feret, aspect ratio, circularity, orientation in nm; optional watershed separation) |
| **Provenance** | W3C PROV model: every file read is fingerprinted (SHA-256) and every operation records its parameters, inputs, outputs, timing, software versions, person, instrument and facility. Export as PROV-JSON |
| **Save** | NeXus/HDF5 `.nxs` (NXentry / NXdata / NXinstrument), Zarr and TIFF, each carrying metadata and provenance; `nuscope crate` packages datasets as an RO-Crate ready for a repository deposit with a DOI |
| **Globus** | `load("globus://<collection>/<path>")` streams a file over HTTPS from a Globus Connect Server collection into a local cache; `ls`, `find`, `download` with checksums, and managed `transfer_to` between collections (instrument PC → Quest → laptop). Login uses the Globus native-app flow |

## Install

```bash
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -e ".[all]"        # core + Globus + Studio + plotting
```

## NUScope Studio

```bash
nuscope studio /path/to/data --open
```

A browser application for the whole workflow, with no installation beyond the package. It runs on your own
machine and nothing leaves it.

- **Library**: browse and search a data folder, drop files from your computer, or browse a Globus collection.
- **Viewer**: calibrated scale bar, colour bar, colour maps (including Northwestern purple), contrast with a
  live histogram, gamma and log display, and position and value readout under the cursor. Stacks get a frame
  slider. Spectrum images and 4D-STEM data show a summed image; click with the pick tool to see the spectrum or
  diffraction pattern at that point.
- **Info**: instrument, beam, optics, acquisition and sample cards from the normalized metadata, plus the full
  original vendor metadata as a searchable tree.
- **Analyze**: noise and contrast, denoise, background removal, Fourier transform, radial profile, particles
  (with outlines drawn on the image), line profile, pixel-size correction and binning. Results that are images
  open as new datasets linked to their source.
- **History**: the provenance of the open dataset, its source files with SHA-256, and PROV-JSON download.
- **Save and share**: `.nxs`, `.tif` or `.zarr`; figures as PNG, PDF, TIFF or SVG with scale bar; an RO-Crate
  zip for a repository deposit. Exports go to `nuscope_exports/` in the data folder.

## Command line

```bash
nuscope info sample.dm4                        # what is in a file (any supported format, or a globus:// URL)
nuscope convert sample.tif sample.nxs          # convert, keeping metadata and provenance
nuscope provenance sample.nxs --prov-json prov.json
nuscope crate deposit/ a.nxs b.nxs --title "Ti alloy BSE series" --author "Roberto dos Reis|https://orcid.org/..."
nuscope globus setup <client-id>               # once, see below
nuscope globus login <collection-id>
nuscope globus ls <collection-id> /path
nuscope globus get globus://<collection-id>/path/file.dm4
nuscope globus transfer globus://<src>/run1 globus://<dst>/run1 --recursive --wait
nuscope tomo studio projects/run                # NUScope-TOMO, when installed
```

## Globus at NUANCE

1. Register NUScope once as a **native app** at <https://app.globus.org/settings/developers> and store its client id:
   `nuscope globus setup <client-id>` (or set `NUSCOPE_GLOBUS_CLIENT_ID`).
2. Find the collection id of the instrument or storage collection in the Globus web app (Collections → Overview).
3. `nuscope globus login <collection-id>` opens a Northwestern login link once; refresh tokens are kept under
   `~/.globus/app/`.
4. Direct reads need a Globus Connect Server v5 collection with HTTPS enabled; for any other collection, or for
   large datasets, use `transfer_to` / `nuscope globus transfer`, which is managed and checksum-verified.

Provenance of a Globus read records the collection id, the path, when it was fetched and the file's SHA-256.

## Tests

`pytest` runs 20 tests. They cover:

- the vendor readers on synthetic instrument files (Thermo Fisher with data bar, Quanta copied sidecar, Hitachi,
  JEOL, Zeiss) and MRC through RosettaSciIO;
- round trips through `.nxs`, `.zarr` and `.tif`;
- provenance chaining and PROV-JSON;
- particle sizes and FFT periodicities against known geometry;
- RO-Crate export;
- the Globus listing, download, cache and transfer paths with mocked services;
- the command line;
- the Studio web API (open, view, analyse, save, figure, RO-Crate).

The readers have also been checked on real NUANCE files (Hitachi S-3400 TIFF + TXT, Gatan DM4 ADF, EELS SI
and 4D diffraction).

## History and credits

NUScope is created and led by Roberto dos Reis (@rmsreis). The first NUScope instrument loaders and the PyQt
viewer (`NUScopeGUI_v0.py`, `ImageLoadLibraries_v0.py`, kept in this repository) were written by Nathaniel Kabat.
The package in `src/nuscope` (v0.2) generalizes those loaders and adds the metadata schema, provenance, analysis,
saving and Globus layers.

## License

MIT, see [LICENSE](LICENSE).
