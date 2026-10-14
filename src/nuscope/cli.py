"""``nuscope`` command line.

    nuscope info <file | globus://collection/path>     what is in a file
    nuscope convert <in> <out.h5|.nxs|.zarr|.tif>      convert, keeping metadata and provenance, sealed
    nuscope provenance <file> [--prov-json out.json]   history of a NUScope file
    nuscope verify <files...>                          check seals, hash chains and signatures
    nuscope sign <files...> [--role ...]               add your signature to sealed files
    nuscope keys create "Name" [--orcid ...] | show | export <file> | trust <file.pub.json> | list
    nuscope crate <out folder> <files...> --title ...  RO-Crate package for a repository deposit
    nuscope formats                                    supported formats
    nuscope studio [folder] [--port 8770] [--open]     browser application
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
    p.add_argument("--no-sign", action="store_true", help="seal without signing, even if you have a key")
    p = sub.add_parser("verify", help="check seals, hash chains and signatures")
    p.add_argument("files", nargs="+")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("sign", help="add your signature to sealed NUScope files")
    p.add_argument("files", nargs="+")
    p.add_argument("--role", default="co-signer", help="e.g. author, co-signer, facility, reviewer")
    k = sub.add_parser("keys", help="your signing key and the keys you trust")
    ks = k.add_subparsers(dest="kcmd", required=True)
    x = ks.add_parser("create", help="create your Ed25519 signing key")
    x.add_argument("name")
    x.add_argument("--orcid")
    x.add_argument("--overwrite", action="store_true")
    ks.add_parser("show", help="your public key and fingerprint")
    x = ks.add_parser("export", help="write your public key to share with others")
    x.add_argument("file")
    x = ks.add_parser("trust", help="trust a public key someone shared (.pub.json)")
    x.add_argument("file")
    ks.add_parser("list", help="keys you trust")
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
    p = sub.add_parser("studio", help="launch NUScope Studio in the browser")
    p.add_argument("folder", nargs="?", default=".")
    p.add_argument("--port", type=int, default=8770)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--open", action="store_true", help="open the browser")
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
        out = ns.save(ns.load(a.source), a.dest, overwrite=a.overwrite, sign=False if a.no_sign else None)
        print(f"wrote {out}")
        print(ns.verify(out))
    elif a.cmd == "verify":
        bad = 0
        for f in a.files:
            r = ns.verify(f)
            bad += not r.ok
            print(json.dumps(r.to_dict(), indent=2) if a.json else f"{f}\n{r}\n")
        return 1 if bad else 0
    elif a.cmd == "sign":
        for f in a.files:
            print(f"{f}\n{ns.integrity.cosign(f, role=a.role)}\n")
    elif a.cmd == "keys":
        return _keys(a)
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
    elif a.cmd == "studio":
        from .studio import serve
        serve(a.folder, host=a.host, port=a.port, open_browser=a.open)
    elif a.cmd == "formats":
        print("\n".join(ns.formats()))
    elif a.cmd == "globus":
        return _globus(a)
    return 0


def _keys(a) -> int:
    from . import integrity as ni
    if a.kcmd == "create":
        k = ni.create_key(a.name, orcid=a.orcid, overwrite=a.overwrite)
        print(f"created key {k.fingerprint} for {k.name}\nprivate key: {ni.home() / 'keys' / ni.KEY_FILE} (keep it safe)"
              "\nshare your public key with: nuscope keys export my_key.pub.json")
    elif a.kcmd in ("show", "export"):
        k = ni.my_key()
        if k is None:
            print('no key yet; create one with: nuscope keys create "Your Name"')
            return 1
        if a.kcmd == "export":
            Path(a.file).write_text(json.dumps(k.to_dict(), indent=2))
            print(f"wrote {a.file}")
        else:
            print(f"{k.name}{f' ({k.orcid})' if k.orcid else ''}\nfingerprint {k.fingerprint}\npublic key  {k.public_key}")
    elif a.kcmd == "trust":
        k = ni.trust(a.file)
        print(f"trusted {k.name} [{k.fingerprint}]")
    elif a.kcmd == "list":
        for fp, k in ni.trusted().items():
            print(f"{fp}  {k['name']}{'  ' + k['orcid'] if k.get('orcid') else ''}")
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
