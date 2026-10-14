# Changelog

## 0.4.1 — 2026-10-14

- Requires Python 3.11 or newer: Zarr 3, which NUScope uses, does not install on 3.10. NUScope 0.4.0
  declared 3.10 by mistake.

## 0.4.0 — 2026-10-13

- **Shared identity.** Signing uses the researcher identity of EMDataBridge (name, validated ORCID iD,
  Ed25519 key), shared with NUScope-TOMO and NUANCE-MCP. Keys made by 0.3 are imported; files signed by 0.3
  still verify. The person in provenance comes from the identity.
- **NUANCE-MCP plugin.** Every acquisition is saved as a sealed, signed `.h5`; new tools `nuscope_describe`,
  `nuscope_verify`, `nuscope_history`, `nuscope_analyze`, `nuscope_list`, `nuscope_identity`.
- `nuscope keys untrust`; one-line CLI errors instead of tracebacks.
- Documentation site.

## 0.3.0

- **Integrity.** SHA-256 hash-chained provenance; a seal in every saved file; Ed25519 signatures,
  countersigning and trust; verification on every read; `nuscope verify | sign | keys`.
- Save as `.h5`.
- **NUScope Studio**: library, calibrated viewer, spectrum and 4D pick, metadata cards, analysis tools,
  history with seal check, save, figure export, RO-Crate.
- Hitachi burned-in data bars removed; stage position in mm.

## 0.2.0

- The NUScope package: readers for Thermo Fisher/FEI, Zeiss, Hitachi and JEOL with one metadata schema,
  RosettaSciIO for 40+ formats, analysis in physical units, W3C PROV provenance, NeXus/Zarr/TIFF, RO-Crate,
  Globus.
