# NUScope Studio

```bash
nuscope studio /path/to/data --open        # http://127.0.0.1:8770
```

A browser application for the whole workflow. It runs on your own computer; nothing leaves it.

| Area | What you can do |
|---|---|
| **Library** | Browse and search the data folder, drop files from your computer, browse a Globus collection. Opened files and the results made from them are listed under *Open*, linked to their source. |
| **Viewer** | Calibrated scale bar (nm, µm, mm, or 1/µm for FFTs), colour bar, colour maps including Northwestern purple, contrast with a live histogram, gamma and log display, position and value under the cursor, frame slider for stacks. |
| **Spectrum images and 4D-STEM** | A summed image is shown; the pick tool shows the EELS spectrum or the diffraction pattern at the clicked pixel. |
| **Info** | Instrument, beam, optics, acquisition and sample cards, and the full original metadata as a searchable tree. |
| **Analyze** | Noise and contrast, denoise, background removal, Fourier transform, radial profile, particles (outlines drawn on the image), line profile, pixel-size correction and binning. Results stay with the dataset they came from. |
| **History** | The seal check (each part and each signature, with whether you trust the key), the provenance timeline, source files with SHA-256, PROV-JSON download. Create your signing identity here. |
| **Save and export** | `.h5`, `.nxs`, `.tif` or `.zarr`, sealed and signed; figures as PNG, PDF, TIFF or SVG with scale bar; an RO-Crate zip. Exports go to `nuscope_exports/` in the data folder. |

Light and dark themes follow your system and can be switched in the header. Open datasets survive a page
reload; a file that changed on disk is read again when reopened.

Options: `--port`, `--host` (default `127.0.0.1`; keep it local unless you know who can reach the port).
