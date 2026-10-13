"""Provenance-tracking decorator for analysis operations."""
from __future__ import annotations

import functools
import inspect

import pandas as pd

from ..dataset import Dataset
from ..provenance import now


def tracked(op: str):
    """Record the call as a provenance activity on the returned dataset(s) or table."""
    def deco(fn):
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(ds: Dataset, *args, **kwargs):
            started = now()
            bound = sig.bind(ds, *args, **kwargs)
            bound.apply_defaults()
            params = {k: v for k, v in list(bound.arguments.items())[1:]}
            out = fn(ds, *args, **kwargs)
            used = [ds.provenance.current] if ds.provenance.current else []
            if isinstance(out, Dataset):
                prov = out.provenance if out.provenance is not ds.provenance else ds.provenance.copy()
                out.provenance = prov
                eid = prov.add_array(out.numpy(), label=f"{op}({ds.name})")
                prov.record(op, params, used=used, generated=[eid], started=started)
            elif isinstance(out, pd.DataFrame):
                prov = ds.provenance.copy()
                eid = f"table:{op}:{id(out):x}"
                from ..provenance import Entity
                prov.entities[eid] = Entity(id=eid, kind="table", label=f"{op}({ds.name})",
                                            attributes={"rows": len(out), "columns": list(map(str, out.columns))})
                prov.record(op, params, used=used, generated=[eid], started=started)
                out.attrs["provenance"] = prov
                out.attrs["source"] = ds.name
            elif isinstance(out, dict):
                out["provenance"] = ds.provenance.copy()
                out["provenance"].record(op, params, used=used, started=started)
            return out
        wrapper.op = op
        return wrapper
    return deco


__all__ = ["tracked"]
