"""Tags: a signed record beside an instrument file, which stays untouched.

Raw files on facility storage must not change, so a seal can't go inside them.
``nuscope tag`` writes ``<file name>.nuscope.json`` beside each file instead, holding

* the SHA-256 and size of the file and its companions (the ``.txt`` of a Hitachi or
  JEOL image, for example);
* the instrument: vendor, model, serial number and, for an exact match, its DOI;
* the key metadata;
* signatures, in the same form as a NUScope seal.

A tag says "this exact file was received from this instrument". It travels with
the file through Globus or any copy, and ``nuscope verify`` and ``ns.load()``
check it wherever the file ends up.

An instrument DOI is recorded only when the registry has this instrument's
serial number and the file records the same one, so a file from another
microscope of the same model is never credited to a NUANCE instrument.

Tagging is safe to repeat, which is what a folder watcher needs: tagged, unchanged
files are skipped, and a file that no longer matches its tag is reported and its
tag left in place, because that is the evidence.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional

from . import metadata as md
from .integrity import Report, make_tag_seal, seal_id, verify_signatures
from .provenance import now, sha256_file

TAG_SUFFIX = ".nuscope.json"
TAG_SCHEMA = "nuscope.tag/1"
COMPANIONS = (".txt", ".hdr")
# what a facility folder holds; NUScope's own .h5 / .nxs files carry their seal inside
INSTRUMENT_FILES = {".tif", ".tiff", ".dm3", ".dm4", ".emd", ".ser", ".emi", ".bcf", ".mrc", ".mib", ".spx"}


def tag_path(path) -> Path:
    path = Path(path)
    return path.with_name(path.name + TAG_SUFFIX)    # the full name: a.tif and a.dm4 can share a folder


def _entry(path: Path) -> dict:
    return {"name": path.name, "size": path.stat().st_size, "sha256": sha256_file(path)}


def _companions(path: Path) -> list[Path]:
    return [c for c in (path.with_suffix(s) for s in COMPANIONS) if c.is_file() and c != path]


def _instrument(meta: dict) -> tuple[dict, list[dict]]:
    """The file's instrument, and its DOI only if the serial numbers match exactly."""
    ins = meta.get("instrument") or {}
    found = {k: ins[k] for k in ("vendor", "model", "serial") if ins.get(k)}
    doi = ins.get("doi")
    if not doi:
        return found, []
    try:
        from nuance_datacite import registry
        known = registry.get(doi)
    except ImportError:
        return found, []
    if known is None or not known.serial or known.serial.strip().lower() != str(ins.get("serial", "")).strip().lower():
        return found, []
    return found, [{"doi": doi, "name": known.name, "status": known.status}]


def tag_file(path, *, sign: Optional[bool] = None, role: str = "facility", overwrite: bool = False) -> dict:
    """Write the tag of one file and return it. The file itself is only read."""
    from .io import load
    path = Path(path)
    dest = tag_path(path)
    if dest.exists() and not overwrite:
        raise FileExistsError(f"{dest.name} exists (pass overwrite=True to replace it)")
    ds = load(path)
    instrument, dois = _instrument(ds.metadata)
    manifest = {
        "schema": TAG_SCHEMA, "created": now(),
        "files": [_entry(p) for p in (path, *_companions(path))],
        "instrument": instrument, "instruments": dois,
        "summary": md.summary(ds.metadata),
        "acquired": md.get(ds.metadata, "acquisition.datetime"),
    }
    tag = make_tag_seal(manifest, sign=sign, role=role)
    tmp = dest.with_name(dest.name + ".tmp")      # never leave half a tag behind
    tmp.write_text(json.dumps(tag, indent=1, ensure_ascii=False) + "\n")
    os.replace(tmp, dest)
    return tag


def verify_tag(tag_file_path) -> Report:
    """Check a tag and the files it describes."""
    tag_file_path = Path(tag_file_path)
    tag = json.loads(tag_file_path.read_text())
    man = tag["manifest"]
    checks, problems = {}, []
    for f in man["files"]:
        p = tag_file_path.with_name(f["name"])
        if not p.is_file():
            checks[f["name"]] = False
            problems.append(f"{f['name']} is missing")
        elif sha256_file(p) != f["sha256"]:
            checks[f["name"]] = False
            problems.append(f"{f['name']} changed after it was tagged")
        else:
            checks[f["name"]] = True
    sigs, bad = verify_signatures(tag)
    problems += bad
    intact = all(checks.values()) and not bad
    status = ("signed" if sigs else "sealed") if intact else "tampered"
    return Report(status, seal_id=seal_id(tag), checks=checks, signatures=sigs, problems=problems,
                  sealed_at=man.get("created"), instruments=man.get("instruments", []))


def find_files(paths: Iterable, recursive: bool = False) -> Iterator[Path]:
    """Instrument files among ``paths`` (files or folders), skipping NUScope's own exports."""
    for p in map(Path, paths):
        if p.is_dir():
            for f in sorted(p.rglob("*") if recursive else p.iterdir()):
                if f.is_file() and f.suffix.lower() in INSTRUMENT_FILES and "nuscope_exports" not in f.parts \
                        and not f.name.startswith("."):
                    yield f
        else:
            yield p


@dataclass
class Result:
    path: Path
    state: str          # tagged | skipped | changed | failed
    detail: str = ""


def tag_many(paths: Iterable, *, recursive: bool = False, sign: Optional[bool] = None, role: str = "facility",
             overwrite: bool = False) -> list[Result]:
    """Tag files and folders. Safe to run again and again on the same folder."""
    out = []
    for f in find_files(paths, recursive):
        dest = tag_path(f)
        try:
            if dest.exists() and not overwrite:
                rep = verify_tag(dest)
                out.append(Result(f, "skipped") if rep.ok else Result(f, "changed", "; ".join(rep.problems)))
                continue
            tag_file(f, sign=sign, role=role, overwrite=overwrite)
            out.append(Result(f, "tagged"))
        except Exception as e:      # one unreadable file must not stop the whole folder
            out.append(Result(f, "failed", f"{type(e).__name__}: {e}"))
    return out


__all__ = ["tag_file", "verify_tag", "tag_many", "tag_path", "find_files", "Result", "TAG_SUFFIX"]
