"""DataCite: instrument DOIs inside every dataset, and DOIs for datasets.

With ``nuance-datacite`` installed (``pip install "nuscope[datacite]"``):

* **Reading** a file looks its instrument up in the NUANCE instrument registry
  (vendor, model, serial) and records the instrument DOI in
  ``metadata["instrument"]["doi"]`` and in the provenance agent of the
  instrument. Saving puts the instrument DOIs in the seal manifest as well, so
  the seal (and every signature on it) covers which instrument collected the
  data. Pixels are never modified.
* **Citing** a sealed file builds DataCite metadata for a dataset DOI linked to
  the instrument (``IsCollectedBy``), to the exact file (seal id and SHA-256)
  and to its creators (ORCID iDs from the file's signatures), and can create a
  *draft* DOI. The DOI is then written next to the seal (not into it: the seal
  must not change), and the DataCite record carries the seal id, so each
  points to the other.

    import nuscope as ns
    from nuscope import datacite
    attrs = datacite.dataset_payload("ti11.h5", title="Ti alloy BSE, sample 11")
    doi = datacite.register_draft("ti11.h5", title="Ti alloy BSE, sample 11")   # needs DataCite credentials
"""
from __future__ import annotations

import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import metadata as md


def available() -> bool:
    try:
        import nuance_datacite  # noqa: F401
        return True
    except ImportError:
        return False


def _need():
    try:
        import nuance_datacite
        return nuance_datacite
    except ImportError as e:
        raise ImportError('DOIs need nuance-datacite: pip install "nuscope[datacite]"') from e


def link_instrument(meta: dict) -> Optional[dict]:
    """Add the registered instrument DOI to ``meta`` (in place). Returns the reference, or None."""
    if not available():
        return None
    from nuance_datacite import registry
    ins = meta.get("instrument") or {}
    if ins.get("doi"):
        return {"doi": ins["doi"]}
    try:
        hit = registry.find(ins.get("vendor"), ins.get("model"), ins.get("serial"))
    except Exception:            # a broken user registry must never stop a file from loading
        return None
    if hit is None:
        return None
    md.put(meta, "instrument.doi", hit.doi)
    md.put(meta, "instrument.doi_status", hit.status)
    md.put(meta, "instrument.name", hit.name)
    md.put(meta, "instrument.facility", hit.facility)
    return hit.as_reference()


# ------------------------------------------------------------------ dataset DOIs
_FORMATS = {".h5": "application/x-hdf5", ".nxs": "application/x-hdf5", ".tif": "image/tiff",
            ".tiff": "image/tiff", ".zarr": "application/x-zarr"}


def dataset_payload(path, *, title: str, description: str = "", creators: Optional[list] = None,
                    url: Optional[str] = None, doi: Optional[str] = None, prefix: Optional[str] = None,
                    subjects: tuple = ()) -> dict:
    """DataCite ``attributes`` for a dataset DOI of a sealed, intact NUScope file."""
    dc = _need()
    from .integrity import verify
    from .io import read_document
    from .provenance import sha256_file
    path = Path(path)
    rep = verify(path)
    if not rep.ok:
        raise ValueError(f"{path.name} is {rep.status}; only intact sealed files can be cited")
    _, doc = read_document(path)
    meta = doc["metadata"]
    man = doc["seal"]["manifest"]
    instruments = man.get("instruments") or ([{"doi": meta["instrument"]["doi"]}]
                                             if (meta.get("instrument") or {}).get("doi") else [])
    if creators is None:
        creators = [dc.payloads.creator(s["name"], s.get("orcid"))
                    for s in rep.signatures if s["valid"] and s.get("role") in ("author", None)]
        if not creators:
            from .integrity import my_key
            me = my_key()
            if me is None:
                raise ValueError("no creators: sign the file, create an identity, or pass creators=[...]")
            creators = [dc.payloads.creator(me.name, me.orcid)]
    file_sha = sha256_file(path) if path.is_file() else None
    return dc.payloads.dataset_attributes(
        title=title, description=description, creators=creators, instruments=instruments,
        seal_id=rep.seal_id, file_name=path.name, file_sha256=file_sha,
        file_size=path.stat().st_size if path.is_file() else None,
        file_format=_FORMATS.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0],
        collected=md.get(meta, "acquisition.datetime"), technique=meta.get("technique"),
        subjects=[s for s in (*subjects, md.get(meta, "sample.name")) if s], url=url, doi=doi, prefix=prefix)


def register_draft(path, *, title: str, client=None, **kw) -> str:
    """Create a draft dataset DOI for ``path`` and record it next to the file's seal. Returns the DOI."""
    dc = _need()
    from .io import read_document, write_seal
    client = client or dc.DataCite()
    attrs = dataset_payload(path, title=title, **kw)
    out = client.create_draft(attrs)["data"]["attributes"]
    _, doc = read_document(Path(path))
    seal = doc["seal"]
    seal.setdefault("identifiers", []).append({
        "doi": out["doi"], "state": out.get("state", "draft"), "datacite": client.environment,
        "registered_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    write_seal(Path(path), seal)
    return out["doi"]


__all__ = ["available", "link_instrument", "dataset_payload", "register_draft"]
