"""Data provenance for NUANCE datasets, modelled on W3C PROV.

Every dataset carries a :class:`Provenance` record:

* **entities**: the things that exist, such as an instrument file (with
  SHA-256, size and modification time, or the Globus collection and path it
  came from) or an in-memory array (with a content hash);
* **activities**: what was done, such as reading a file or running an
  analysis, with its parameters, timing and the software versions used;
* **agents**: who and what was responsible, such as the person, the
  facility (NUANCE Center) and the instrument.

The record travels with the data through every analysis, is written into
every file NUScope saves, and exports to PROV-JSON or RO-Crate.
"""
from __future__ import annotations

import copy
import getpass
import hashlib
import os
import platform
import socket
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

FACILITY = "NUANCE Center, Northwestern University"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


def hash_array(data) -> str:
    """Content hash of an array (BLAKE2b over dtype, shape and bytes)."""
    import numpy as np
    a = np.ascontiguousarray(np.asarray(data))
    h = hashlib.blake2b(digest_size=20)
    h.update(str(a.dtype).encode())
    h.update(str(a.shape).encode())
    h.update(a.tobytes())
    return h.hexdigest()


def software_versions(extra: tuple[str, ...] = ()) -> dict[str, str]:
    from . import __version__
    out = {"nuscope": __version__, "python": platform.python_version()}
    for mod in ("numpy", "scipy", "skimage", "rsciio", "h5py", "zarr", "tifffile", "globus_sdk") + extra:
        m = sys.modules.get(mod)
        if m is not None:
            out[mod] = str(getattr(m, "__version__", "?"))
    return out


@dataclass
class Agent:
    id: str
    kind: str                       # "person" | "organization" | "instrument" | "software"
    name: str
    orcid: Optional[str] = None
    attributes: dict = field(default_factory=dict)


@dataclass
class Entity:
    id: str
    kind: str                       # "file" | "array" | "table" | "remote"
    label: str = ""
    sha256: Optional[str] = None
    content_hash: Optional[str] = None
    size: Optional[int] = None
    location: Optional[str] = None  # local path or URL (globus://collection/path)
    created: Optional[str] = None
    attributes: dict = field(default_factory=dict)


@dataclass
class Activity:
    id: str
    op: str
    started: str
    ended: Optional[str] = None
    params: dict = field(default_factory=dict)
    used: list = field(default_factory=list)        # entity ids
    generated: list = field(default_factory=list)   # entity ids
    agents: list = field(default_factory=list)      # agent ids
    software: dict = field(default_factory=dict)
    host: str = ""


def _current_person() -> Agent:
    user = os.environ.get("NUSCOPE_USER") or getpass.getuser()
    return Agent(id=f"person:{user}", kind="person", name=os.environ.get("NUSCOPE_USER_NAME", user),
                 orcid=os.environ.get("NUSCOPE_ORCID"))


def _jsonable(v: Any):
    import numpy as np
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, (np.integer, np.floating, np.bool_)):
        return v.item()
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, Path):
        return str(v)
    if hasattr(v, "shape") and hasattr(v, "dtype"):
        return f"<array {tuple(v.shape)} {v.dtype}>"
    return repr(v)


class Provenance:
    """A small PROV graph that is copied forward with every derived dataset."""

    def __init__(self):
        self.entities: dict[str, Entity] = {}
        self.activities: list[Activity] = []
        self.agents: dict[str, Agent] = {}
        self.current: Optional[str] = None      # id of the entity this dataset is
        fac = Agent(id="org:nuance", kind="organization", name=FACILITY,
                    attributes={"ror": "https://ror.org/000e0be47"})
        self.agents[fac.id] = fac

    # ---------------------------------------------------------------- building
    def copy(self) -> "Provenance":
        return copy.deepcopy(self)

    def add_agent(self, agent: Agent) -> str:
        self.agents.setdefault(agent.id, agent)
        return agent.id

    def add_instrument(self, metadata: dict) -> Optional[str]:
        ins = (metadata or {}).get("instrument") or {}
        name = " ".join(str(x) for x in (ins.get("vendor"), ins.get("model")) if x)
        if not name:
            return None
        aid = f"instrument:{name.replace(' ', '_')}" + (f":{ins['serial']}" if ins.get("serial") else "")
        return self.add_agent(Agent(id=aid, kind="instrument", name=name, attributes=_jsonable(ins)))

    def add_file(self, path: str | Path, *, location: Optional[str] = None, hash_file: bool = True,
                 attributes: Optional[dict] = None) -> str:
        p = Path(path)
        st = p.stat()
        digest = sha256_file(p) if hash_file else None
        eid = f"file:sha256:{digest}" if digest else f"file:{uuid.uuid4().hex}"
        self.entities[eid] = Entity(
            id=eid, kind="file" if location is None else "remote", label=p.name, sha256=digest,
            size=st.st_size, location=location or str(p.resolve()),
            created=datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds"),
            attributes=attributes or {})
        return eid

    def add_array(self, data, label: str = "") -> str:
        h = hash_array(data)
        eid = f"array:blake2b:{h}"
        self.entities.setdefault(eid, Entity(id=eid, kind="array", label=label, content_hash=h,
                                             created=now(),
                                             attributes={"shape": list(getattr(data, "shape", ())),
                                                         "dtype": str(getattr(data, "dtype", ""))}))
        return eid

    def record(self, op: str, params: Optional[dict] = None, used: Optional[list] = None,
               generated: Optional[list] = None, started: Optional[str] = None,
               instrument: Optional[str] = None) -> Activity:
        person = self.add_agent(_current_person())
        agents = [person, "org:nuance"] + ([instrument] if instrument else [])
        act = Activity(id=f"activity:{uuid.uuid4().hex[:12]}", op=op, started=started or now(), ended=now(),
                       params=_jsonable(params or {}), used=list(used or []), generated=list(generated or []),
                       agents=agents, software=software_versions(), host=socket.gethostname())
        self.activities.append(act)
        if act.generated:
            self.current = act.generated[-1]
        return act

    def merge(self, other: "Provenance"):
        """Bring in another dataset's history (for operations with several inputs)."""
        self.entities.update(other.entities)
        self.agents.update(other.agents)
        seen = {a.id for a in self.activities}
        self.activities.extend(a for a in other.activities if a.id not in seen)

    # ---------------------------------------------------------------- reading
    def lineage(self) -> list[str]:
        """Human-readable history, oldest first."""
        out = []
        for a in self.activities:
            used = ", ".join(self.entities[u].label or u for u in a.used if u in self.entities) or "-"
            ps = ", ".join(f"{k}={v}" for k, v in a.params.items()) or "no parameters"
            out.append(f"{a.ended or a.started}  {a.op}({ps})  from {used}")
        return out

    def sources(self) -> list[Entity]:
        return [e for e in self.entities.values() if e.kind in ("file", "remote")]

    # ---------------------------------------------------------------- export
    def to_dict(self) -> dict:
        return {"schema": "nuscope.provenance/1", "current": self.current,
                "entities": [asdict(e) for e in self.entities.values()],
                "activities": [asdict(a) for a in self.activities],
                "agents": [asdict(a) for a in self.agents.values()]}

    @classmethod
    def from_dict(cls, d: dict) -> "Provenance":
        p = cls()
        p.entities = {e["id"]: Entity(**e) for e in d.get("entities", [])}
        p.activities = [Activity(**a) for a in d.get("activities", [])]
        p.agents.update({a["id"]: Agent(**a) for a in d.get("agents", [])})
        p.current = d.get("current")
        return p

    def to_prov_json(self) -> dict:
        """W3C PROV-JSON (https://www.w3.org/submissions/prov-json/)."""
        doc: dict[str, Any] = {"prefix": {"nuscope": "https://github.com/NUANCE-IT/NUScope#"},
                               "entity": {}, "activity": {}, "agent": {},
                               "used": {}, "wasGeneratedBy": {}, "wasAssociatedWith": {}}
        q = lambda s: "nuscope:" + s.replace(":", "_")  # noqa: E731
        for e in self.entities.values():
            doc["entity"][q(e.id)] = {"prov:label": e.label, "prov:type": e.kind,
                                      **({"nuscope:sha256": e.sha256} if e.sha256 else {}),
                                      **({"prov:location": e.location} if e.location else {})}
        for a in self.agents.values():
            doc["agent"][q(a.id)] = {"prov:label": a.name, "prov:type": a.kind,
                                     **({"nuscope:orcid": a.orcid} if a.orcid else {})}
        for i, a in enumerate(self.activities):
            doc["activity"][q(a.id)] = {"prov:label": a.op, "prov:startTime": a.started,
                                        "prov:endTime": a.ended, "nuscope:params": a.params}
            for j, u in enumerate(a.used):
                doc["used"][f"_:u{i}_{j}"] = {"prov:activity": q(a.id), "prov:entity": q(u)}
            for j, g in enumerate(a.generated):
                doc["wasGeneratedBy"][f"_:g{i}_{j}"] = {"prov:entity": q(g), "prov:activity": q(a.id)}
            for j, ag in enumerate(a.agents):
                doc["wasAssociatedWith"][f"_:w{i}_{j}"] = {"prov:activity": q(a.id), "prov:agent": q(ag)}
        return doc


__all__ = ["Provenance", "Entity", "Activity", "Agent", "sha256_file", "hash_array", "FACILITY"]
