# Tagging instrument files

Raw files on facility storage must not change, so a seal can't go inside them. `nuscope tag` writes a small
signed file beside each one instead:

```text
sample11.tif                  unchanged
sample11.txt                  unchanged
sample11.tif.nuscope.json     the tag
```

```bash
nuscope tag /rdss/s3400/2026-10-31            # a folder (add -r for subfolders)
nuscope tag sample11.tif
nuscope verify sample11.tif                   # anywhere the file and its tag end up
```

The tag holds the SHA-256 and size of the file and its companions (the `.txt` of a Hitachi or JEOL image), the
instrument's vendor, model and serial number, the key metadata, and signatures. `ns.load()` checks a tag when it
finds one, puts the report in `ds.integrity`, and records the result in the history.

## On facility storage

- **Safe to repeat.** Tagged, unchanged files are skipped, so a scheduled job can run it on the same folder.
- **Changes are reported, not hidden.** If a file no longer matches its tag, `nuscope tag` reports `changed`, keeps the
  old tag as evidence, and exits with status 1. `--overwrite` replaces tags on purpose.
- **Use a service identity.** Create a facility identity on the machine that runs the job. Tags are signed with
  `role: facility`, and a researcher can verify them after trusting that key.
- **One bad file doesn't stop a folder.** It's reported as `failed` and the rest continue.

## Which instrument

A tag records the instrument's DOI only when the registry has this instrument's serial number and the file records
the same one. A file from another microscope of the same model is never credited to a NUANCE instrument. A file
with no serial number is tagged without a DOI.

## With Globus

Globus copies files byte for byte, so a tag stays valid. Transfer the **folder** so the tags go with the files. A file
copied without its tag reports `NO SEAL`: nothing is wrong with it, but it can't be checked.

!!! note "What a tag proves"
    A tag proves the file hasn't changed since it was tagged. If tagging happens on RDSS, that says nothing about
    the time between the microscope and RDSS. To close that gap, tag on the acquisition computer.
