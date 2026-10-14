# Installation

NUScope needs Python 3.10 or newer.

```bash
pip install nuscope                  # core: readers, analysis, saving, provenance, integrity
pip install "nuscope[studio]"        # + NUScope Studio (browser application)
pip install "nuscope[globus]"        # + reading from Globus collections
pip install "nuscope[all]"           # everything
```

With [uv](https://docs.astral.sh/uv/):

```bash
uv venv --python 3.12 && source .venv/bin/activate
uv pip install "nuscope[all]"
```

From source, for development:

```bash
git clone https://github.com/NUANCE-IT/NUScope.git
cd NUScope
uv pip install -e ".[all,dev]"
pytest
```

## Optional packages

| Extra | Adds | For |
|---|---|---|
| `studio` | FastAPI, Uvicorn, Matplotlib, imageio | `nuscope studio` |
| `globus` | globus-sdk | `globus://` URLs, `nuscope globus ...` |
| `plot` | Matplotlib | `Dataset.plot()` |
| `all` | all of the above, plus `mrcfile` | |

NUScope depends on [EMDataBridge](https://github.com/NUANCE-IT/EMDataBridge) for the researcher identity
used to sign files. Installing NUScope installs it.

## Your identity (once)

To sign the files you save, create your identity: your name, your ORCID iD and an Ed25519 key.

```bash
emdb identity create "Your Name" --orcid 0000-0000-0000-0000
```

The ORCID check digit is validated. See [Integrity and signatures](guide/integrity.md).
