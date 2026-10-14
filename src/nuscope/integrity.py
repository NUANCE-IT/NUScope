"""Cryptographic integrity for NUScope files: seals, signatures and verification.

Every file NUScope saves carries a **seal**, a manifest of SHA-256 hashes of

* the data array (dtype, shape and bytes),
* the axes (calibration),
* the metadata (normalized and original vendor metadata, name, signal type),
* the full provenance record, whose steps also form a hash chain
  (see :mod:`nuscope.provenance`).

The seal can be **signed** with Ed25519 keys. A person creates a key once
(``nuscope keys create``); the private key stays in ``~/.nuscope/keys`` and the
public key travels inside every signature. Others can add their own
signature to the same seal, for example a facility manager countersigning
an acquisition (``nuscope sign``). Keys are trusted by adding them to
``~/.nuscope/trusted_keys.json`` (``nuscope keys trust``); your own key is
trusted automatically.

Reading a file verifies it: :attr:`Dataset.integrity` holds the report, a
warning is raised if anything changed after sealing, and the result is
recorded in the provenance of the reopened dataset.

    import nuscope as ns
    ns.integrity.create_key("Roberto dos Reis", orcid="https://orcid.org/...")
    ns.save(ds, "grain.h5")              # sealed and signed
    print(ns.verify("grain.h5"))         # data, metadata, history, signatures
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .provenance import Provenance, canonical, now, sha256_json

SEAL_SCHEMA = "nuscope.seal/1"
KEY_FILE = "nuscope_ed25519.pem"
PUB_FILE = "nuscope_ed25519.pub.json"


def home() -> Path:
    return Path(os.environ.get("NUSCOPE_HOME", Path.home() / ".nuscope")).expanduser()


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


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
    }


def seal_id(seal: dict) -> str:
    return sha256_json(seal["manifest"])


# ------------------------------------------------------------------ keys
@dataclass
class KeyInfo:
    name: str
    orcid: Optional[str]
    public_key: str          # base64 raw Ed25519 public key
    fingerprint: str
    created: str = ""

    def to_dict(self) -> dict:
        return dict(vars(self))


def fingerprint(public_key_b64: str) -> str:
    """Short, readable key id: SHA-256 of the raw public key, 16 hex digits in groups of four."""
    h = hashlib.sha256(base64.b64decode(public_key_b64)).hexdigest()[:16]
    return ":".join(h[i:i + 4] for i in range(0, 16, 4))


def _crypto():
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
        return serialization, ed25519
    except ImportError as e:  # pragma: no cover
        raise ImportError("Signing needs the 'cryptography' package: pip install cryptography") from e


def create_key(name: str, orcid: Optional[str] = None, *, passphrase: Optional[str] = None,
               overwrite: bool = False) -> KeyInfo:
    """Create your Ed25519 signing key in ``~/.nuscope/keys`` (private key readable only by you)."""
    serialization, ed25519 = _crypto()
    kdir = home() / "keys"
    if (kdir / KEY_FILE).exists() and not overwrite:
        raise FileExistsError(f"a key already exists in {kdir} (pass overwrite=True to replace it)")
    kdir.mkdir(parents=True, exist_ok=True)
    os.chmod(kdir, 0o700)
    sk = ed25519.Ed25519PrivateKey.generate()
    passphrase = passphrase or os.environ.get("NUSCOPE_KEY_PASSPHRASE")
    enc = (serialization.BestAvailableEncryption(passphrase.encode()) if passphrase
           else serialization.NoEncryption())
    pem = sk.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, enc)
    fd = os.open(kdir / KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(pem)
    pub = _b64(sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
    info = KeyInfo(name=name, orcid=orcid or None, public_key=pub, fingerprint=fingerprint(pub), created=now())
    (kdir / PUB_FILE).write_text(json.dumps(info.to_dict(), indent=2))
    trust(info)
    return info


def my_key() -> Optional[KeyInfo]:
    """Your public key information, or None if you have not created a key."""
    p = home() / "keys" / PUB_FILE
    if not (p.exists() and (home() / "keys" / KEY_FILE).exists()):
        return None
    return KeyInfo(**json.loads(p.read_text()))


def _private_key(passphrase: Optional[str] = None):
    serialization, _ = _crypto()
    passphrase = passphrase or os.environ.get("NUSCOPE_KEY_PASSPHRASE")
    pem = (home() / "keys" / KEY_FILE).read_bytes()
    return serialization.load_pem_private_key(pem, password=passphrase.encode() if passphrase else None)


def trusted() -> dict[str, dict]:
    p = home() / "trusted_keys.json"
    return json.loads(p.read_text()) if p.exists() else {}


def trust(key: KeyInfo | dict | str | Path) -> KeyInfo:
    """Trust a public key: a KeyInfo, its dict, or a ``.pub.json`` file someone shared with you."""
    if isinstance(key, (str, Path)):
        key = json.loads(Path(key).read_text())
    if isinstance(key, dict):
        key = KeyInfo(**{k: key.get(k) for k in ("name", "orcid", "public_key", "fingerprint", "created")})
    if fingerprint(key.public_key) != key.fingerprint:
        raise ValueError("the fingerprint does not match the public key")
    t = trusted()
    t[key.fingerprint] = key.to_dict() | {"trusted_at": now()}
    home().mkdir(parents=True, exist_ok=True)
    (home() / "trusted_keys.json").write_text(json.dumps(t, indent=2))
    return key


# ------------------------------------------------------------------ sealing and signing
def _signed_part(seal: dict, signer: dict) -> bytes:
    return canonical({"seal": seal_id(seal), "signer": signer})


def sign_seal(seal: dict, *, role: str = "author", passphrase: Optional[str] = None) -> dict:
    """Add your signature to a seal (in place) and return the signature entry."""
    info = my_key()
    if info is None:
        raise FileNotFoundError("no signing key; create one with nuscope keys create \"Your Name\"")
    if any(s["signer"]["fingerprint"] == info.fingerprint for s in seal.get("signatures", [])):
        raise ValueError("this seal already carries your signature")
    signer = {"name": info.name, "orcid": info.orcid, "fingerprint": info.fingerprint,
              "public_key": info.public_key, "alg": "Ed25519", "role": role, "signed_at": now()}
    sig = _private_key(passphrase).sign(_signed_part(seal, signer))
    entry = {"signer": signer, "signature": _b64(sig)}
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
        out += [f"  ! {p}" for p in self.problems]
        return "\n".join(out)


def verify_signature(seal: dict, entry: dict) -> bool:
    _, ed25519 = _crypto()
    signer = entry["signer"]
    try:
        if fingerprint(signer["public_key"]) != signer["fingerprint"]:
            return False
        pk = ed25519.Ed25519PublicKey.from_public_bytes(base64.b64decode(signer["public_key"]))
        pk.verify(base64.b64decode(entry["signature"]), _signed_part(seal, signer))
        return True
    except Exception:
        return False


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
    tr = trusted()
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
                  sealed_at=m.get("created"))


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


__all__ = ["create_key", "my_key", "trust", "trusted", "make_seal", "sign_seal", "verify", "verify_doc",
           "cosign", "Report", "KeyInfo", "fingerprint", "sha256_array", "home"]
