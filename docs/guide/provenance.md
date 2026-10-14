# Provenance

Every dataset carries a provenance record modelled on [W3C PROV](https://www.w3.org/TR/prov-overview/):

- **entities**: what exists. Instrument files are recorded with their SHA-256, size, modification time and
  location (or the Globus collection and path they came from). Arrays are recorded by a content hash
  (BLAKE2b over dtype, shape and bytes).
- **activities**: what was done: reading a file, each analysis step, saving. Each records its operation name,
  parameters, inputs and outputs, start and end time, host, and the versions of NUScope, Python and the
  libraries in use (NumPy, SciPy, scikit-image, RosettaSciIO, h5py, Zarr, tifffile, globus-sdk).
- **agents**: who and what was responsible: you (your name and ORCID iD from your
  [identity](integrity.md#your-identity)), the instrument, NUANCE Center (with its ROR id) and the software.

```python
print("\n".join(ds.provenance.lineage()))
ds.provenance.sources()          # the instrument files, with SHA-256
ds.provenance.to_prov_json()     # W3C PROV-JSON
```

The record is copied forward with every derived dataset, merged when an operation has several inputs, and
written into every file NUScope saves. Reopening a NUScope file adds a step saying which file was read and
whether its seal checked out.

## The hash chain

Each step stores `digest`, the SHA-256 of its own canonical JSON, and `prev`, the digests of the steps it
follows. Entity ids are content addresses (`file:sha256:…`, `array:blake2b:…`), so each step also pins its
exact inputs and outputs. Editing a parameter, a time or an input afterwards changes the digest and breaks the
links to every later step:

```python
ok, problems = ds.provenance.check_chain()
```

When histories are merged, a step can follow several earlier ones, so the record is a chain of hashes over
a directed acyclic graph, not a single list.
