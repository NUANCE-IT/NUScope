# DOIs: instruments and datasets

NUANCE registers its instruments in [DataCite](https://datacite.org) (repository
[NU.NUANCE](https://doi.datacite.org/repositories/nu.nuance), prefix `10.82427`). NUScope connects every dataset
to the DOI of the instrument that collected it, and can give the dataset its own DOI. The connection is part
of the file's [seal](integrity.md), so it can't be changed afterwards.

```bash
pip install "nuscope[datacite]"          # adds nuance-datacite
```

## Instrument DOIs in every file

When NUScope reads a file, it matches the instrument (vendor, model, serial number) against the NUANCE
instrument registry of [nuance-datacite](https://github.com/NUANCE-IT/NUANCE-Data-Cite). For a match it records:

- `metadata["instrument"]["doi"]`, with `name`, `facility` and `doi_status`;
- the instrument in the provenance, identified as `instrument:doi:<doi>`;
- when saving, the instrument DOI in the seal manifest (`"instruments": [...]`), next to the hashes.

The metadata hash, the provenance hash and the manifest all cover the DOI, and every signature covers the
manifest. Changing the instrument afterwards breaks the seal. **No pixel is modified**.

```text
$ nuscope verify ti11.h5
SIGNED AND INTACT  seal de6c55f300e19608…
  …
  instrument EPIC SEM Hitachi S-3400 https://doi.org/10.82427/nuance.epic.sem.s3400.2025.000001
```

```bash
nuance-datacite instruments --check        # the registry, and which DOIs DataCite shows as public
nuance-datacite find --vendor Hitachi --model S-3400
```

Add instruments (or override entries) with a JSON file at `$NUANCE_INSTRUMENTS` or
`~/.nuance/instruments.json`, in the same shape as the packaged registry.

## A DOI for a dataset

```bash
nuscope cite ti11.h5 --title "Ti alloy BSE, sample 11"            # print the DataCite JSON
nuscope cite ti11.h5 --title "..." --out ti11.datacite.json
nuscope cite ti11.h5 --title "..." --draft                         # create a DRAFT DOI
```

Only intact, sealed files can be cited. The DataCite metadata links:

| Link | DataCite field |
|---|---|
| the instrument(s) that collected the data | `relatedIdentifiers`, `relationType: IsCollectedBy` → instrument DOI |
| the exact file | `alternateIdentifiers`: `sha256:<seal id>` (type `NUScope seal SHA-256`) and the file's SHA-256 |
| the people | `creators` with ORCID iDs, taken from the file's valid author signatures (or your identity) |
| when | `dates`, `Collected`, from the acquisition date |

`--draft` creates a **draft** DOI with your DataCite credentials (`DATACITE_REPOSITORY_ID`,
`DATACITE_PASSWORD`, `DATACITE_PREFIX`, `DATACITE_ENVIRONMENT`, from the environment or a `.env` file;
`test` by default). The DOI is then written **next to** the seal, not into it, so the seal and its signatures
stay valid. The DOI record carries the seal id, so each points to the other.

Publishing a DOI makes it findable and permanent. nuance-datacite never does this on its own: you have to
repeat the DOI as confirmation, and on production also set `DATACITE_ALLOW_PRODUCTION_PUBLISH=1`.

```python
from nuscope import datacite
attrs = datacite.dataset_payload("ti11.h5", title="Ti alloy BSE, sample 11")
doi = datacite.register_draft("ti11.h5", title="Ti alloy BSE, sample 11")
```

!!! note "DOI watermarks in pixels"
    Some NUANCE tools can hide a DOI inside the image pixels (LSB steganography). That changes the data,
    so NUScope does not do it. The seal already binds the file to its DOIs without touching a pixel.
