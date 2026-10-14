# File layout

## HDF5 (`.h5`, `.nxs`)

```text
/                                   NX_class=NXroot, creator=NUScope
  @nuscope_seal                     seal id (SHA-256 of the manifest)
  @nuscope_signed_by                "Name [fingerprint]; ..." or "unsigned"
  entry/                            NXentry, definition NXem (SEM/TEM/STEM/FIB) or NXdata
    title
    data/                           NXdata, signal=data
      data                          the array (gzip), @sha256
      <axis name>                   axis values, @units
    instrument/                     NXinstrument: vendor, model ... as attributes
      beam/ optics/ detector/ acquisition/ sample/
    nuscope/                        NXcollection, @name, @signal, @seal_id
      metadata                      JSON
      original_metadata             JSON
      axes                          JSON
      provenance                    JSON (nuscope.provenance/1)
      seal                          JSON (nuscope.seal/1)
```

## Zarr (`.zarr`)

The array is `data`; the NUScope document (`name`, `signal`, `axes`, `metadata`, `original_metadata`,
`provenance`, `seal`) is in the group attribute `nuscope`.

## TIFF (`.tif`)

The image description starts with `NUScope dataset v1` on its own line, followed by the NUScope document as
JSON. Resolution tags carry the pixel size.

## The seal (`nuscope.seal/1`)

```json
{
  "manifest": {
    "schema": "nuscope.seal/1",
    "created": "2026-10-13T23:19:22.320+00:00",
    "data": {"sha256": "…", "dtype": "<f4", "shape": [448, 640]},
    "axes_sha256": "…",
    "metadata_sha256": "…",
    "provenance_sha256": "…",
    "provenance_heads": ["…"],
    "steps": 3,
    "instruments": [{"doi": "10.82427/nuance.epic.sem.s3400.2025.000001", "name": "EPIC SEM Hitachi S-3400"}]
  },
  "signatures": [
    {"signer": {"name": "…", "orcid": "https://orcid.org/…", "fingerprint": "…", "public_key": "…",
                "alg": "Ed25519", "role": "author", "signed_at": "…"},
     "signature": "…"}
  ]
}
```

Hashes are SHA-256 of canonical JSON (sorted keys, no whitespace, UTF-8). The data hash covers the dtype, the
shape and the C-ordered bytes. A signature covers `{"seal": <seal id>, "signer": <signer record>}`.
