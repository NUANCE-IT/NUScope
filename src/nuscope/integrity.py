"""Cryptographic integrity for NUScope files: seals, signatures and verification.

Every file NUScope saves carries a **seal**, a manifest of SHA-256 hashes of

* the data array (dtype, shape and bytes),
* the axes (calibration),
* the metadata (normalized and original vendor metadata, name, signal type),
* the full provenance record, whose steps also form a hash chain
  (see :mod:`nuscope.provenance`).

The seal can be **signed**. Signing uses the researcher identity of
:mod:`EMDataBridge.identity`, shared with NUScope-TOMO and NUANCE-MCP: a name,
a validated ORCID iD and an Ed25519 key, created once with
``emdb identity create`` (or ``nuscope keys create``). The private key stays on
your computer; the public key travels inside every signature. Others can add
their own signature to the same seal, for example a facility manager
countersigning an acquisition (``nuscope sign``). Keys are trusted with
``emdb identity trust``; your own key is trusted automatically.

Reading a file verifies it: :attr:`Dataset.integrity` holds the report, a
warning is raised if anything changed after sealing, and the result is
recorded in the provenance of the reopened dataset.

    import nuscope as ns
    ns.integrity.create_key("Your Name", orcid="0000-0002-1825-0097")
    ns.save(ds, "grain.h5")              # sealed and signed
    print(ns.verify("grain.h5"))         # data, metadata, history, signatures
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from EMDataBridge import identity
from EMDataBridge.identity import Identity, fingerprint  # noqa: F401  (re-exported)

from .provenance import Provenance, now, sha256_json

SEAL_SCHEMA = "nuscope.seal/1"
KeyInfo = Identity   # NUScope 0.3 name


# ------------------------------------------------------------------ hashing
def sha256_array(data) -> str:
    """SHA-256 over dtype, shape and C-ordered bytes, so the hash does not depend on the file format."""
    a = np.ascontiguousarray(np.asarray(data))
    h = hashlib.sha256()
    h.update(a.dtype.str.encode())
    h.update(json.dumps(list(a.shape)).encode())
    h.update(a.reshape(-1).view(np.uint8))
    return h.hexdigest()


def manifest(data, doc: dict) -> dict:
    """What a seal pins down. ``doc`` is the NUScope document stored next to the data in a file."""
    a = np.asarray(data)
    prov = doc["provenance"]
    return {
        "schema": SEAL_SCHEMA,
        "created": now(),
        "data": {"sha256": sha256_array(a), "dtype": a.dtype.str, "shape": list(a.shape)},
        "axes_sha256": sha256_json(doc["axes"]),
        "metadata_sha256": sha256_json({k: doc.get(k) for k in ("name", "signal", "metadata", "original_metadata")}),
        "provenance_sha256": sha256_json(prov),
        "provenance_heads": Provenance.from_dict(prov).heads(),
        "steps": len(prov.get("activities", [])),
        # instrument DOIs (DataCite): named in the manifest so every signature covers them explicitly
        "instruments": instruments_of(prov),
    }


def instruments_of(prov: dict) -> list[dict]:
    """The registered instruments (with DOIs) among a provenance record's agents."""
    out = {}
    for a in prov.get("agents", []):
        doi = (a.get("attributes") or {}).get("doi")
        if a.get("kind") == "instrument" and doi:
            out[doi] = {"doi": doi, "name": (a.get("attributes") or {}).get("name") or a.get("name")}
    return [out[k] for k in sorted(out)]


def seal_id(seal: dict) -> str:
    return sha256_json(seal["manifest"])


# ------------------------------------------------------------------ keys (EMDataBridge identity)
def create_key(name: str, orcid: Optional[str] = None, *, passphrase: Optional[str] = None,
               overwrite: bool = False) -> Identity:
    """Create your identity and signing key (see :func:`EMDataBridge.identity.create`)."""
    return identity.create(name, orcid=orcid, passphrase=passphrase, overwrite=overwrite)


def my_key() -> Optional[Identity]:
    """Your identity, or None if you have not created one."""
    return identity.me()


trusted = identity.trusted
trust = identity.trust
untrust = identity.untrust


# ------------------------------------------------------------------ sealing and signing
def sign_seal(seal: dict, *, role: str = "author", passphrase: Optional[str] = None) -> dict:
    """Add your signature to a seal (in place) and return the signature entry."""
    me = identity.me()
    if me is None:
        raise FileNotFoundError('no signing key; create one with: emdb identity create "Your Name" --orcid ...')
    if any(s["signer"]["fingerprint"] == me.fingerprint for s in seal.get("signatures", [])):
        raise ValueError("this seal already carries your signature")
    entry = identity.sign({"seal": seal_id(seal)}, role=role, passphrase=passphrase)
    seal.setdefault("signatures", []).append(entry)
    return entry


def make_seal(data, doc: dict, *, sign: Optional[bool] = None, role: str = "author") -> dict:
    """Seal a document. ``sign=None`` signs when you have a key, ``True`` requires one, ``False`` never signs."""
    seal = {"manifest": manifest(data, doc), "signatures": []}
    if sign or (sign is None and my_key() is not None):
        sign_seal(seal, role=role)
    return seal


# ------------------------------------------------------------------ verification
@dataclass
class Report:
    """Result of checking a file. ``status`` is one of
    ``signed`` (intact, at least one valid signature), ``sealed`` (intact, not signed),
    ``tampered`` (something changed after sealing) or ``unsealed`` (no seal: a vendor file
    or a file written before NUScope 0.3)."""
    status: str
    seal_id: Optional[str] = None
    checks: dict = field(default_factory=dict)        # data / axes / metadata / provenance / chain -> bool
    signatures: list = field(default_factory=list)    # {name, orcid, fingerprint, role, signed_at, valid, trusted}
    problems: list = field(default_factory=list)
    sealed_at: Optional[str] = None
    instruments: list = field(default_factory=list)   # instrument DOIs named in the (verified) manifest
    identifiers: list = field(default_factory=list)   # dataset DOIs recorded next to the seal (not covered by it)

    @property
    def ok(self) -> bool:
        return self.status in ("signed", "sealed")

    def to_dict(self) -> dict:
        return dict(vars(self)) | {"ok": self.ok}

    def __str__(self) -> str:
        head = {"signed": "SIGNED AND INTACT", "sealed": "INTACT (sealed, not signed)",
                "tampered": "CHANGED AFTER SEALING", "unsealed": "NO SEAL"}[self.status]
        out = [f"{head}" + (f"  seal {self.seal_id[:16]}…" if self.seal_id else "")]
        if self.sealed_at:
            out.append(f"  sealed {self.sealed_at}")
        for k, v in self.checks.items():
            out.append(f"  {'✓' if v else '✗'} {k}")
        for s in self.signatures:
            mark = "✓" if s["valid"] else "✗"
            who = s["name"] + (f" ({s['orcid']})" if s.get("orcid") else "")
            out.append(f"  {mark} signed by {who}, key {s['fingerprint']}, {s['role']}, {s['signed_at']}"
                       + ("" if not s["valid"] else ", trusted" if s["trusted"] else ", key not in your trusted list"))
        for i in self.instruments:
            out.append(f"  instrument {i.get('name') or ''} https://doi.org/{i['doi']}")
        for d in self.identifiers:
            out.append(f"  dataset DOI {d['doi']} ({d.get('state')}, {d.get('datacite')} DataCite)")
        out += [f"  ! {p}" for p in self.problems]
        return "\n".join(out)


def verify_signature(seal: dict, entry: dict) -> bool:
    return identity.verify({"seal": seal_id(seal)}, entry).valid


def verify_doc(data, doc: dict) -> Report:
    """Check data and document against the seal stored in the document."""
    seal = doc.get("seal")
    chain_ok, chain_problems = Provenance.from_dict(doc["provenance"]).check_chain()
    if not seal:
        return Report("unsealed", checks={"history chain": chain_ok} if doc["provenance"].get("activities") else {},
                      problems=["the file has no seal"] + chain_problems)
    m = seal["manifest"]
    a = np.asarray(data)
    checks = {
        "data": m["data"]["sha256"] == sha256_array(a),
        "calibration": m["axes_sha256"] == sha256_json(doc["axes"]),
        "metadata": m["metadata_sha256"] == sha256_json({k: doc.get(k) for k in
                                                        ("name", "signal", "metadata", "original_metadata")}),
        "history": m["provenance_sha256"] == sha256_json(doc["provenance"]),
        "history chain": chain_ok,
    }
    problems = [f"{k} changed after sealing" for k, v in checks.items() if not v and k != "history chain"]
    problems += chain_problems
    tr = identity.trusted()
    sigs = []
    for e in seal.get("signatures", []):
        s = e["signer"]
        valid = verify_signature(seal, e)
        sigs.append({k: s.get(k) for k in ("name", "orcid", "fingerprint", "role", "signed_at")}
                    | {"valid": valid, "trusted": valid and s["fingerprint"] in tr})
        if not valid:
            problems.append(f"the signature of {s.get('name')} does not match")
    intact = all(checks.values()) and all(s["valid"] for s in sigs)
    status = ("signed" if sigs else "sealed") if intact else "tampered"
    return Report(status, seal_id=seal_id(seal), checks=checks, signatures=sigs, problems=problems,
                  sealed_at=m.get("created"), instruments=m.get("instruments", []),
                  identifiers=seal.get("identifiers", []))


def verify(path) -> Report:
    """Verify a NUScope file (.nxs, .h5, .zarr or .tif) without loading it as a dataset."""
    from .io import read_document
    data, doc = read_document(Path(path))
    return verify_doc(data, doc)


def cosign(path, *, role: str = "co-signer", passphrase: Optional[str] = None) -> Report:
    """Add your signature to an existing sealed file, after checking that it is intact."""
    from .io import read_document, write_seal
    path = Path(path)
    data, doc = read_document(path)
    rep = verify_doc(data, doc)
    if rep.status not in ("signed", "sealed"):
        raise ValueError(f"{path.name} is {rep.status}; only intact sealed files can be signed")
    seal = doc["seal"]
    sign_seal(seal, role=role, passphrase=passphrase)
    write_seal(path, seal)
    return verify(path)


__all__ = ["create_key", "my_key", "trust", "trusted", "untrust", "make_seal", "sign_seal", "verify", "verify_doc",
           "cosign", "Report", "Identity", "KeyInfo", "fingerprint", "sha256_array"]
