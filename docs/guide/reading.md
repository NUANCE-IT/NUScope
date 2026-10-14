# Reading files

```python
import nuscope as ns
ds = ns.load(path)                 # first dataset in the file
items = ns.load_all(path)          # every dataset in the file
print(ns.formats())                # everything NUScope can read
```

`load()` accepts a local path or a `globus://<collection>/<path>` URL (see [Globus](globus.md)).

## What is read natively

| Instrument family | File | Metadata source |
|---|---|---|
| Thermo Fisher / FEI (Quanta, Helios, Scios, Nova, Apreo) | `.tif` | TIFF tag 34682 / 34680 (INI text), or a copied `.txt`/`.hdr` sidecar |
| Zeiss | `.tif` | TIFF tag 34118 (`CZ_SEM`) |
| Hitachi (S-4800, SU8030, S-3400) | `.tif` + `.txt` | `[SemImageFile]` sidecar |
| JEOL (JSM-7900F) | `.tif` + `.txt` | `$CM_` / `$SM_` sidecar |
| NUScope files | `.h5`, `.nxs`, `.zarr`, `.tif` | embedded NUScope document (verified on read) |

**Data bars** burned into SEM images are removed by default (`crop_databar=True`), and the number of rows
removed is recorded in `acquisition.databar_rows_removed` and in the history. Pass `crop_databar=False` to keep
them.

## Through RosettaSciIO

Everything else goes through [RosettaSciIO](https://hyperspy.org/rosettasciio/): Gatan DigitalMicrograph
DM3/DM4 (with Microscope Info, DigiScan, Session Info and EELS tags mapped to the NUScope schema), Thermo Fisher
Velox EMD, TIA SER/EMI, JEOL, Bruker BCF, EDAX, MRC, Quantum Detectors MIB, EMPAD, Delmic, PantaRhei and more.
Large files can be opened lazily with `lazy=True`.

## What you get

A [`Dataset`](../api/dataset.md): the array, calibrated axes, the normalized metadata, the vendor's original
metadata and the provenance.

```python
ds.axes            # [Axis(name='y', size=448, scale=396.875, units='nm'), Axis(name='x', ...)]
ds.pixel_size_nm   # 396.875
ds.signal          # image | spectrum | spectrum_image | diffraction | stack
ds.metadata        # normalized: see Metadata
ds.original_metadata
ds.provenance.lineage()
```

The type of data follows from the axes: an energy axis in eV makes a spectrum or spectrum image, reciprocal
axes (1/nm) make diffraction or 4D-STEM data.
