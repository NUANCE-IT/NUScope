# Configuration

| Variable | Default | Used for |
|---|---|---|
| `EMDATABRIDGE_HOME` | `~/.emdatabridge` | your identity (`identity/`) and trusted keys |
| `EMDATABRIDGE_KEY_PASSPHRASE` | unset | encrypts / unlocks your private key (`NUSCOPE_KEY_PASSPHRASE` also works) |
| `NUSCOPE_HOME` | `~/.nuscope` | where NUScope 0.3 kept signing keys (imported into your identity on first use) |
| `NUSCOPE_CACHE` | `~/.nuscope/cache` | files fetched from Globus |
| `NUSCOPE_GLOBUS_CLIENT_ID` | from `~/.nuscope/config.json` (written by `nuscope globus setup`) | the Globus native-app client id |
| `NUSCOPE_USER`, `NUSCOPE_USER_NAME`, `NUSCOPE_ORCID` | login name | the person in provenance when you have no identity |
| `NUSCOPE_ACQUISITION_DIR` | `~/NUScope/acquisitions` | files saved from NUANCE-MCP acquisitions |
| `NUSCOPE_SAMPLE` | unset | sample name recorded for NUANCE-MCP acquisitions |
| `NUANCE_INSTRUMENTS` | `~/.nuance/instruments.json` | extra or overriding instrument DOIs |
| `DATACITE_REPOSITORY_ID`, `DATACITE_PASSWORD`, `DATACITE_PREFIX`, `DATACITE_ENVIRONMENT` | `NU.NUANCE`, unset, unset, `test` | `nuscope cite --draft` |
