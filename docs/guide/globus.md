# Globus at NUANCE

NUScope reads files straight from [Globus](https://www.globus.org) collections and moves whole runs between
them.

```python
ds = ns.load("globus://<collection-id>/instrument/2026-10-13/run1/image_001.dm4")
```

## Setup (once)

1. Register NUScope as a **native app** at <https://app.globus.org/settings/developers> and store its client
   id: `nuscope globus setup <client-id>` (or set `NUSCOPE_GLOBUS_CLIENT_ID`).
2. Find the collection id of the instrument or storage collection in the Globus web app
   (Collections → Overview).
3. `nuscope globus login <collection-id>` shows a Northwestern login link once; refresh tokens are kept under
   `~/.globus/app/`.

Install the extra first: `pip install "nuscope[globus]"`.

## Reading and moving data

```bash
nuscope globus ls <collection-id> /path
nuscope globus get globus://<collection-id>/path/file.dm4 [dest]
nuscope globus transfer globus://<src>/run1 globus://<dst>/run1 --recursive --wait
```

```python
from nuscope.globus import GlobusSession
s = GlobusSession()
s.ls(cid, "/path"); s.find(cid, "/", pattern="*.dm4")
s.download(cid, "/path/file.dm4", "file.dm4")          # (path, sha256, bytes)
task = s.transfer_to(src, "/run1", dst, "/run1", recursive=True)
s.wait(task)
```

Direct reads need a Globus Connect Server v5 collection with HTTPS enabled. For any other collection, and for
large data, use a managed transfer, which Globus verifies with checksums. Files read this way are cached in
`~/.nuscope/cache` (or `$NUSCOPE_CACHE`).

The provenance of a Globus read records the collection id, the path, when it was fetched and the file's
SHA-256.
