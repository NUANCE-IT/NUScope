"""Globus integration: read NUANCE data straight from a Globus collection.

Three ways in, all recorded in provenance (collection id, path, checksum):

* ``nuscope.load("globus://<collection-id>/path/to/file.dm4")``: the file is
  streamed over HTTPS from a Globus Connect Server v5 collection into a local
  cache and opened. A file that is already cached with the same size is reused;
* ``GlobusSession().ls(collection, path)``, ``.read_bytes(...)`` and ``.download(...)``
  to browse and fetch;
* ``GlobusSession().transfer(src, src_path, dst, dst_path)`` for large or many
  files: a managed, checksum-verified Globus Transfer between collections
  (e.g. an instrument PC collection to Quest or your laptop's Globus Connect
  Personal).

Authentication uses the Globus SDK's native-app login (a browser link, then a
code pasted back), with refresh tokens stored under ``~/.globus/app``. It needs
a Globus *native app* client id registered for NUScope at
https://app.globus.org/settings/developers, given as ``client_id=`` or the
``NUSCOPE_GLOBUS_CLIENT_ID`` environment variable.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Optional
from urllib.parse import quote

from .provenance import Entity, now

CLIENT_ID_ENV = "NUSCOPE_GLOBUS_CLIENT_ID"
CONFIG = Path.home() / ".nuscope" / "config.json"
CACHE = Path(os.environ.get("NUSCOPE_CACHE", Path.home() / ".nuscope" / "cache"))


class GlobusError(RuntimeError):
    pass


@dataclass
class RemoteFile:
    collection: str
    path: str
    name: str
    type: str
    size: int
    last_modified: str


def parse_url(url: str) -> tuple[str, str]:
    """globus://<collection-id>/<path> -> (collection id, absolute path)."""
    if not url.startswith("globus://"):
        raise ValueError("expected globus://<collection-id>/<path>")
    rest = url[len("globus://"):]
    cid, _, path = rest.partition("/")
    if len(cid) != 36:
        raise ValueError(f"{cid!r} is not a Globus collection id (UUID)")
    return cid, "/" + path


def _configured_client_id() -> Optional[str]:
    if os.environ.get(CLIENT_ID_ENV):
        return os.environ[CLIENT_ID_ENV]
    if CONFIG.exists():
        return json.loads(CONFIG.read_text()).get("globus_client_id")
    return None


class GlobusSession:
    """Talks to Globus Transfer (listing, transfers) and to collections over HTTPS (reads).

    ``transfer_client``, ``http`` and ``auth_header`` can be injected (tests,
    service accounts); by default they come from a Globus ``UserApp`` login.
    """

    def __init__(self, client_id: Optional[str] = None, *, app=None, transfer_client=None, http=None,
                 auth_header: Optional[Callable[[str], str]] = None, app_name: str = "NUScope"):
        self.client_id = client_id or _configured_client_id()
        self._app, self._tc, self._http, self._auth = app, transfer_client, http, auth_header
        self.app_name = app_name
        self._https: dict[str, str] = {}

    # ------------------------------------------------------------ auth
    @property
    def app(self):
        if self._app is None:
            import globus_sdk
            if not self.client_id:
                raise GlobusError(
                    "No Globus client id. Register a native app for NUScope at https://app.globus.org/settings/developers "
                    f"and set {CLIENT_ID_ENV}=<client id> (or run: nuscope globus setup <client id>).")
            self._app = globus_sdk.UserApp(self.app_name, client_id=self.client_id,
                                           config=globus_sdk.GlobusAppConfig(request_refresh_tokens=True))
        return self._app

    def require(self, *collections: str) -> None:
        """Ask for HTTPS access to these collections at the next login."""
        from globus_sdk.scopes import GCSCollectionScopes
        self.app.add_scope_requirements({c: [GCSCollectionScopes(c).https] for c in collections})

    def login(self, *collections: str) -> None:
        if collections:
            self.require(*collections)
        _ = self.transfer
        self.app.login()

    def logout(self) -> None:
        self.app.logout()

    def _header(self, collection: str) -> str:
        if self._auth:
            return self._auth(collection)
        self.require(collection)
        return self.app.get_authorizer(collection).get_authorization_header()

    @property
    def transfer(self):
        if self._tc is None:
            import globus_sdk
            self._tc = globus_sdk.TransferClient(app=self.app)
        return self._tc

    @property
    def http(self):
        if self._http is None:
            import requests
            self._http = requests.Session()
        return self._http

    # ------------------------------------------------------------ browse
    def ls(self, collection: str, path: str = "/", show_hidden: bool = False) -> list[RemoteFile]:
        res = self.transfer.operation_ls(collection, path=path, show_hidden=show_hidden)
        items = res["DATA"] if isinstance(res, dict) or hasattr(res, "__getitem__") else list(res)
        base = path.rstrip("/")
        return [RemoteFile(collection, f"{base}/{d['name']}", d["name"], d["type"], int(d.get("size") or 0),
                           d.get("last_modified", "")) for d in items]

    def find(self, collection: str, path: str = "/", pattern: str = "*", max_depth: int = 4) -> Iterator[RemoteFile]:
        """Walk a directory tree (breadth first) yielding files that match a glob pattern."""
        import fnmatch
        queue = [(path, 0)]
        while queue:
            p, depth = queue.pop(0)
            for f in self.ls(collection, p):
                if f.type == "dir" and depth < max_depth:
                    queue.append((f.path, depth + 1))
                elif f.type == "file" and fnmatch.fnmatch(f.name, pattern):
                    yield f

    def stat(self, collection: str, path: str) -> Optional[RemoteFile]:
        parent, _, name = path.rstrip("/").rpartition("/")
        return next((f for f in self.ls(collection, parent or "/") if f.name == name), None)

    def https_server(self, collection: str) -> str:
        if collection not in self._https:
            ep = self.transfer.get_endpoint(collection)
            url = ep.get("https_server") if hasattr(ep, "get") else ep["https_server"]
            if not url:
                raise GlobusError(f"Collection {collection} has no HTTPS access (needs Globus Connect Server v5). "
                                  "Use GlobusSession.transfer_to() to move the data instead.")
            self._https[collection] = url.rstrip("/")
        return self._https[collection]

    # ------------------------------------------------------------ read
    def _get(self, collection: str, path: str):
        url = f"{self.https_server(collection)}/{quote(path.lstrip('/'))}"
        r = self.http.get(url, headers={"Authorization": self._header(collection)}, stream=True, timeout=60)
        if getattr(r, "status_code", 200) in (401, 403):
            raise GlobusError(f"Access to {path} on {collection} was refused ({r.status_code}). "
                              "Log in again with: nuscope globus login " + collection)
        r.raise_for_status()
        return r

    def read_bytes(self, collection: str, path: str) -> bytes:
        return self._get(collection, path).content

    def download(self, collection: str, path: str, dest: str | Path, chunk: int = 1 << 22) -> tuple[Path, str, int]:
        """Stream a file to ``dest``; returns (path, sha256, size)."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        h, n = hashlib.sha256(), 0
        tmp = dest.with_suffix(dest.suffix + ".part")
        with self._get(collection, path) as r, open(tmp, "wb") as f:
            for block in r.iter_content(chunk):
                f.write(block)
                h.update(block)
                n += len(block)
        tmp.replace(dest)
        return dest, h.hexdigest(), n

    # ------------------------------------------------------------ transfer
    def transfer_to(self, src: str, src_path: str, dst: str, dst_path: str, *, label: str = "NUScope transfer",
                    recursive: bool = False, sync_level: str = "checksum") -> str:
        """Submit a checksum-verified Globus Transfer; returns the task id."""
        import globus_sdk
        td = globus_sdk.TransferData(src, dst, label=label, sync_level=sync_level, verify_checksum=True)
        td.add_item(src_path, dst_path, recursive=recursive)
        return self.transfer.submit_transfer(td)["task_id"]

    def wait(self, task_id: str, timeout: int = 3600, poll: int = 15) -> dict:
        self.transfer.task_wait(task_id, timeout=timeout, polling_interval=poll)
        return dict(self.transfer.get_task(task_id).data)


_default: Optional[GlobusSession] = None


def session() -> GlobusSession:
    global _default
    if _default is None:
        _default = GlobusSession()
    return _default


def fetch(url: str, session: Optional[GlobusSession] = None, cache_dir: Optional[Path] = None,
          refresh: bool = False) -> tuple[Path, Entity]:
    """Download a globus:// URL into the cache; return (local path, provenance entity)."""
    s = session or globals()["session"]()
    cid, path = parse_url(url)
    local = Path(cache_dir or CACHE) / cid / path.lstrip("/")
    meta = s.stat(cid, path)
    if meta is None:
        raise FileNotFoundError(f"{path} not found on collection {cid}")
    started = now()
    reused = local.exists() and not refresh and local.stat().st_size == meta.size
    if reused:
        from .provenance import sha256_file
        digest, size = sha256_file(local), local.stat().st_size
    else:
        local, digest, size = s.download(cid, path, local)
    ent = Entity(id=f"remote:sha256:{digest}", kind="remote", label=Path(path).name, sha256=digest, size=size,
                 location=url, created=meta.last_modified,
                 attributes={"globus_collection": cid, "globus_path": path, "fetched": started,
                             "from_cache": reused, "https_server": s._https.get(cid)})
    return local, ent


__all__ = ["GlobusSession", "GlobusError", "RemoteFile", "parse_url", "fetch", "session"]
