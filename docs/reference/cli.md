# Command line

```text
nuscope info <file | globus://collection/path> [--json]   what is in a file
nuscope convert <in> <out.h5|.nxs|.zarr|.tif> [--overwrite] [--no-sign]
nuscope verify <files...> [--json]                        seals, hash chains, signatures (exit 1 if any fails)
nuscope sign <files...> [--role ROLE]                     add your signature to intact sealed files
nuscope cite <file> --title T [--description D] [--url U] [--out F] [--draft]
                                                          DataCite dataset-DOI metadata; --draft registers a draft
nuscope provenance <file> [--prov-json out.json]          the history of a NUScope file
nuscope crate <folder> <files...> --title T [--description D] [--author "Name|ORCID"]
nuscope formats                                           supported formats
nuscope studio [folder] [--port 8770] [--host 127.0.0.1] [--open]
nuscope keys create "Name" [--orcid ID] [--overwrite] | show | export <file> | trust <file> | untrust <fp> | list
nuscope globus setup <client-id> | login [collection...] | ls <collection> [path]
               | get <url> [dest] | transfer <src-url> <dst-url> [--recursive] [--wait]
```

`nuscope keys ...` manages the same identity as `emdb identity ...` from EMDataBridge.

Other NUScope modules add command groups through the `nuscope.commands` entry point: with NUScope-TOMO
installed, `nuscope tomo run recipe.yaml`, `nuscope tomo studio project/` and so on.

Errors (a missing file, an unsupported format) are reported in one line, and the exit status is 2.
