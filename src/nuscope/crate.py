"""Package datasets and their provenance as an RO-Crate 1.1 (https://w3id.org/ro/crate/1.1),
ready for a repository deposit with a DOI (e.g. Northwestern Arch, Zenodo)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Iterable, Optional

from .dataset import Dataset
from .integrity import verify
from .provenance import FACILITY, now, sha256_file


def write_crate(datasets: Iterable[Dataset], folder: str | Path, *, title: str, description: str = "",
                license: str = "https://creativecommons.org/licenses/by/4.0/", authors: Optional[list[dict]] = None,
                include_sources: bool = False, fmt: str = ".nxs") -> Path:
    """Write each dataset (as ``fmt``) plus ro-crate-metadata.json describing files, people,
    instruments and every processing step."""
    from .io import save
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    graph: list[dict] = [
        {"@id": "ro-crate-metadata.json", "@type": "CreativeWork", "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
         "about": {"@id": "./"}},
        {"@id": "#nuance", "@type": "Organization", "name": FACILITY, "url": "https://www.nuance.northwestern.edu",
         "identifier": "https://ror.org/000e0be47"},
    ]
    parts, people, actions, things = [], {}, [], {}
    for a in authors or []:
        pid = a.get("orcid") or f"#{a['name'].replace(' ', '_')}"
        people[pid] = {"@id": pid, "@type": "Person", "name": a["name"], "affiliation": {"@id": "#nuance"}}
    for ds in datasets:
        fname = f"{(ds.name or 'dataset').replace('/', '_')}{fmt}"
        path = folder / fname
        save(ds, path, overwrite=True)
        parts.append({"@id": fname})
        rep = verify(path)
        things[fname] = {"@id": fname, "@type": "File", "name": ds.name, "encodingFormat": _mime(fmt),
                         "contentSize": path.stat().st_size, "sha256": sha256_file(path),
                         "description": "; ".join(_summary(ds)),
                         # the seal inside the file: hashes of data, metadata and history, and who signed them
                         "nuscope:seal": rep.seal_id, "nuscope:integrity": rep.status,
                         "nuscope:signedBy": [{"name": g["name"], "fingerprint": g["fingerprint"],
                                               **({"orcid": g["orcid"]} if g.get("orcid") else {})}
                                              for g in rep.signatures if g["valid"]]}
        prov = ds.provenance
        for ag in prov.agents.values():
            if ag.kind == "person":
                pid = ag.orcid or f"#{ag.id}"
                people.setdefault(pid, {"@id": pid, "@type": "Person", "name": ag.name, "affiliation": {"@id": "#nuance"}})
            elif ag.kind == "instrument":
                things.setdefault(f"#{ag.id}", {"@id": f"#{ag.id}", "@type": "IndividualProduct", "name": ag.name})
        for e in prov.sources():
            sid = f"#{e.id}"
            if include_sources and e.location and Path(e.location).exists():
                shutil.copy2(e.location, folder / e.label)
                sid = e.label
                parts.append({"@id": sid})
            things.setdefault(sid, {"@id": sid, "@type": "File", "name": e.label, "sha256": e.sha256,
                                    "contentSize": e.size, **({"url": e.location} if e.location and "://" in e.location else {})})
        for act in prov.activities:
            agent = next((p for p in act.agents if p.startswith("person:")), None)
            ag = prov.agents.get(agent) if agent else None
            actions.append({"@id": f"#{act.id}", "@type": "CreateAction", "name": act.op,
                            "startTime": act.started, "endTime": act.ended,
                            "agent": {"@id": (ag.orcid or f"#{ag.id}") if ag else "#nuance"},
                            "instrument": [{"@id": f"#{x}"} for x in act.agents if x.startswith("instrument:")]
                            + [{"@id": "#nuscope"}],
                            "object": [{"@id": f"#{u}"} for u in act.used],
                            "result": [{"@id": fname}] if act is prov.activities[-1] else [],
                            "description": json.dumps(act.params, default=str)})
    from . import __version__
    graph.append({"@id": "#nuscope", "@type": "SoftwareApplication", "name": "NUScope", "version": __version__,
                  "url": "https://github.com/NUANCE-IT/NUScope"})
    graph.append({"@id": "./", "@type": "Dataset", "name": title, "description": description, "datePublished": now()[:10],
                  "license": {"@id": license}, "publisher": {"@id": "#nuance"}, "hasPart": parts,
                  "author": [{"@id": k} for k in people], "mentions": [{"@id": a["@id"]} for a in actions]})
    graph += list(people.values()) + list(things.values()) + actions
    out = folder / "ro-crate-metadata.json"
    out.write_text(json.dumps({"@context": "https://w3id.org/ro/crate/1.1/context", "@graph": graph}, indent=2, default=str))
    return out


def _mime(fmt: str) -> str:
    return {".nxs": "application/x-hdf5", ".h5": "application/x-hdf5", ".tif": "image/tiff",
            ".zarr": "application/vnd+zarr"}.get(fmt, "application/octet-stream")


def _summary(ds: Dataset) -> list[str]:
    from . import metadata as md
    return md.summary(ds.metadata)


__all__ = ["write_crate"]
