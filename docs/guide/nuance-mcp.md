# NUANCE-MCP

[NUANCE-MCP](https://github.com/NUANCE-IT/NUANCE-MCP) lets an LLM (Claude Desktop, a local Ollama model ...)
drive a microscope through the Model Context Protocol. NUScope plugs into it, so

- **every acquisition is saved as a sealed, signed NUScope file**, with calibrated axes, the column state as
  metadata and the tool call as provenance;
- **the model gets data tools** that work in physical units and check integrity.

```bash
pip install nuance-mcp nuscope          # NUScope-TOMO adds its own tools when installed
emdb identity create "Your Name" --orcid 0000-0000-0000-0000
nuance-mcp serve --adapter simulator     # or gatan, jeol, hitachi
```

The server finds NUScope through the `nuance_mcp.plugins` entry point; `list_plugins` shows what loaded.

!!! note
    Plugin support is new in NUANCE-MCP (the `nuance_mcp.plugins` entry point and acquisition hooks).
    Use a NUANCE-MCP version that includes it.

## Acquisitions

After `acquire_tem_image`, `acquire_stem`, `acquire_4d_stem`, `acquire_diffraction` or `acquire_eels`, the
response gains

```json
"plugins": {"nuscope": {
  "file": "~/NUScope/acquisitions/2026-10-13/211932_528_acquire_stem_SimSTEM.h5",
  "seal": "31ce1e35…", "integrity": "signed",
  "signed_by": ["Your Name [1a2b:3c4d:5e6f:7a8b]"]}}
```

The file records:

- the image or spectrum with calibrated axes (nm for images and scans; eV for spectra);
- the column state (high tension, magnification, mode, focus, stage position, detectors) as metadata;
- the tool and its validated parameters as the first step of the history;
- you, from your identity, as the operator.

Files go to `$NUSCOPE_ACQUISITION_DIR` (default `~/NUScope/acquisitions`), one folder per day.
`NUSCOPE_SAMPLE` sets the sample name.

## Tools

| Tool | What it does |
|---|---|
| `nuscope_describe(path)` | calibration, key metadata and integrity of any supported file |
| `nuscope_verify(path)` | the seal check and signers |
| `nuscope_history(path)` | every step with its parameters, and the source files with SHA-256 |
| `nuscope_analyze(path, op, params)` | `stats`, `denoise`, `fft`, `radial_profile`, `line_profile`, `particles`, ... Image results are saved as new sealed files next to the input |
| `nuscope_list(folder)` | files saved from acquisitions, newest first |
| `nuscope_identity()` | who signs, and where files are saved |

NUScope-TOMO adds `tomo_project`, `tomo_table`, `tomo_volume`, `tomo_ops`, `tomo_run` and `tomo_job`.

Turn plugins off with `nuance-mcp serve --no-plugins`, or choose them with `NUANCE_MCP_PLUGINS=nuscope`.
