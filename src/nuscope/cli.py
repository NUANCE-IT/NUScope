"""``nuscope`` command line.

    nuscope info <file | globus://collection/path>     what is in a file
    nuscope convert <in> <out.nxs|.zarr|.tif>          convert, keeping metadata and provenance
    nuscope provenance <file> [--prov-json out.json]   history of a NUScope file
    nuscope crate <out folder> <files...> --title ...  RO-Crate package for a repository deposit
    nuscope formats                                    supported formats
    nuscope globus setup <client-id> | login [collection...] | ls <collection> [path] | get <url> [dest]
                   | transfer <src-url> <dst-url> [--recursive]

Other NUScope modules add their own command groups through the
``nuscope.commands`` entry point (e.g. ``nuscope tomo ...`` from NUScope-TOMO).
"""
from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import entry_points
from pathlib import Path


def _plugins() -> dict:
    try:
        return {ep.name: ep for ep in entry_points(group="nuscope.commands")}
    except Exception:
        return {}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    plugins = _plugins()
    if argv and argv[0] in plugins:   # hand the rest of the line to the module
        return int(plugins[argv[0]].load()(argv[1:]) or 0)

    from . import __version__
    ap = argparse.ArgumentParser(prog="nuscope", description="NUScope: electron-microscopy data at NUANCE.")
    ap.add_argument("--version", action="version", version=f"NUScope {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("info", help="describe a file")
    p.add_argument("source")
    p.add_argument("--json", action="store_true", help="print normalized metadata as JSON")
    p = sub.add_parser("convert", help="convert to .nxs / .zarr / .tif with provenance")
    p.add_argument("source")
    p.add_argument("dest")
    p.add_argument("--overwrite", action="store_true")
    p = sub.add_parser("provenance", help="show the history of a NUScope file")
    p.add_argument("source")
    p.add_argument("--prov-json", help="also write W3C PROV-JSON here")
    p = sub.add_parser("crate", help="write an RO-Crate with data, metadata and provenance")
    p.add_argument("folder")
    p.add_argument("files", nargs="+")
    p.add_argument("--title", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--author", action="append", default=[], help="'Name' or 'Name|https://orcid.org/...'")
    sub.add_parser("formats", help="list supported formats")
    g = sub.add_parser("globus", help="Globus: setup, login, list, download, transfer")
    gs = g.add_subparsers(dest="gcmd", required=True)
    x = gs.add_parser("setup", help="store the NUScope Globus client id")
    x.add_argument("client_id")
    x = gs.add_parser("login", help="log in to Globus (optionally for collections)")
    x.add_argument("collections", nargs="*")
    x = gs.add_parser("ls", help="list a collection directory")
    x.add_argument("collection")
    x.add_argument("path", nargs="?", default="/")
    x = gs.add_parser("get", help="download globus://collection/path")
    x.add_argument("url")
    x.add_argument("dest", nargs="?")
    x = gs.add_parser("transfer", help="managed transfer between collections")
    x.add_argument("src")
    x.add_argument("dst")
    x.add_argument("--recursive", action="store_true")
    x.add_argument("--wait", action="store_true")
    for name in plugins:
        sub.add_parser(name, help=f"{name} module (see: nuscope {name} --help)")
    a = ap.parse_args(argv)

    import nuscope as ns
    if a.cmd == "info":
        for d in ns.load_all(a.source):
            print(json.dumps(d.metadata, indent=2, default=str) if a.json else d.describe())
    elif a.cmd == "convert":
        out = ns.save(ns.load(a.source), a.dest, overwrite=a.overwrite)
        print(f"wrote {out}")
    elif a.cmd == "provenance":
        d = ns.load(a.source)
        print("\n".join(d.provenance.lineage()))
        if a.prov_json:
            Path(a.prov_json).write_text(json.dumps(d.provenance.to_prov_json(), indent=2))
            print(f"PROV-JSON → {a.prov_json}")
    elif a.cmd == "crate":
        from .crate import write_crate
        authors = [dict(zip(("name", "orcid"), s.split("|", 1))) for s in a.author]
        out = write_crate([ns.load(f) for f in a.files], a.folder, title=a.title, description=a.description,
                          authors=authors)
        print(f"RO-Crate → {out}")
    elif a.cmd == "formats":
        print("\n".join(ns.formats()))
    elif a.cmd == "globus":
        return _globus(a)
    return 0


def _globus(a) -> int:
    from .globus import CONFIG, GlobusSession, parse_url
    if a.gcmd == "setup":
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
        cfg["globus_client_id"] = a.client_id
        CONFIG.write_text(json.dumps(cfg, indent=2))
        print(f"saved Globus client id to {CONFIG}")
        return 0
    s = GlobusSession()
    if a.gcmd == "login":
        s.login(*a.collections)
        print("logged in")
    elif a.gcmd == "ls":
        for f in s.ls(a.collection, a.path):
            print(f"{'d' if f.type == 'dir' else '-'} {f.size:>14,} {f.last_modified[:19]}  {f.name}")
    elif a.gcmd == "get":
        cid, path = parse_url(a.url)
        dest, digest, n = s.download(cid, path, a.dest or Path(path).name)
        print(f"{dest}  {n:,} bytes  sha256 {digest}")
    elif a.gcmd == "transfer":
        (sc, sp), (dc, dp) = parse_url(a.src), parse_url(a.dst)
        tid = s.transfer_to(sc, sp, dc, dp, recursive=a.recursive)
        print(f"task {tid}")
        if a.wait:
            print(json.dumps(s.wait(tid), indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
