"""Ground-truth tests for NUScope: vendor readers on synthetic instrument files,
round trips, provenance, analysis in physical units, RO-Crate and Globus (mocked)."""
import json
from pathlib import Path

import numpy as np
import pytest
import tifffile

import nuscope as ns
from nuscope import analyze as an
from nuscope.globus import GlobusSession, fetch, parse_url

THERMO_INI = """[User]
Date=05/14/2024
Time=10:12:34 AM
User=nuance_user

[System]
Type=SEM
Dnumber=D9999
SystemType=Quanta FEG 650
DisplayWidth=0.47

[Beam]
HV=5000
Spot=3
Beam=EBeam

[EBeam]
HV=5000
BeamCurrent=1.6e-10
WD=0.0101
HFW=1.27e-05

[Scan]
Dwelltime=3e-05
PixelWidth=1.24e-08
PixelHeight=1.24e-08
HorFieldsize=1.27e-05

[Stage]
StageT=0.9128

[Detectors]
Name=ETD
Mode=SE

[Image]
ResolutionX=64
ResolutionY=48
"""


def disks(shape=(256, 256), centers=((60, 60), (60, 180), (180, 120)), r=20, seed=0):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[: shape[0], : shape[1]]
    img = np.full(shape, 40.0)
    for cy, cx in centers:
        img[(yy - cy) ** 2 + (xx - cx) ** 2 <= r * r] = 200
    return np.clip(img + rng.normal(0, 8, shape), 0, 255).astype(np.uint8)


# ------------------------------------------------------------------ vendor readers
def test_thermo_tiff_metadata_and_databar(tmp_path):
    img = np.zeros((60, 64), np.uint8)
    img[48:] = 255                                  # data bar
    p = tmp_path / "quanta.tif"
    tifffile.imwrite(p, img, extratags=[(34682, "s", 0, THERMO_INI, False)])
    d = ns.load(p)
    assert d.shape == (48, 64)                      # data bar cropped
    assert d.pixel_size_nm == pytest.approx(12.4)
    m = d.metadata
    assert m["instrument"]["model"] == "Quanta FEG 650" and m["technique"] == "SEM"
    assert m["beam"]["voltage_kV"] == 5 and m["beam"]["current_nA"] == pytest.approx(0.16)
    assert m["optics"]["working_distance_mm"] == pytest.approx(10.1)
    assert m["optics"]["magnification"] == pytest.approx(0.47 / 1.27e-5, rel=1e-3)
    assert m["detector"] == {"name": "ETD", "mode": "SE"}
    assert m["acquisition"]["dwell_us"] == pytest.approx(30)
    assert m["sample"]["stage"]["tilt_deg"] == pytest.approx(52.3, abs=0.05)
    assert d.original_metadata["Scan"]["PixelWidth"] == "1.24e-08"


def test_quanta_copied_sidecar(tmp_path):
    p = tmp_path / "ResolutionTest_008.tif"
    tifffile.imwrite(p, np.zeros((48, 64), np.uint8))
    (tmp_path / "ResolutionTest_008-COPIED.TXT").write_text(THERMO_INI)
    d = ns.load(p)
    assert d.metadata["instrument"]["vendor"] == "Thermo Fisher Scientific" and d.pixel_size_nm == pytest.approx(12.4)


def test_hitachi_s4800_sidecar(tmp_path):
    p = tmp_path / "tin.tif"
    tifffile.imwrite(p, np.zeros((96, 128), np.uint8))
    (tmp_path / "tin.txt").write_text("[SemImageFile]\nInstructName=S-4800\nSerialNumber=1234\nDate=2019/05/14\n"
                                      "Time=10:23:11\nDataSize=128x96\nPixelSize=9.921875\nSignalName=SE(U)\n"
                                      "AcceleratingVoltage=5000 Volt\nEmissionCurrent=10000 nA\n"
                                      "WorkingDistance=8100 um\nMagnification=10000\n")
    d = ns.load(p)
    m = d.metadata
    assert m["instrument"]["model"] == "S-4800" and m["beam"]["voltage_kV"] == 5
    assert m["optics"]["working_distance_mm"] == pytest.approx(8.1) and m["optics"]["magnification"] == 10000
    assert d.pixel_size_nm == pytest.approx(9.921875) and m["detector"]["name"] == "SE(U)"


def test_jeol_7900_sidecar(tmp_path):
    p = tmp_path / "tt_LED_2.tif"
    tifffile.imwrite(p, np.zeros((96, 128), np.uint8))
    (tmp_path / "tt_LED_2.txt").write_text("$CM_FORMAT JEOL/SEM\n$CM_TITLE tt_LED_2\n$CM_DATE 2020/02/03\n"
                                           "$CM_TIME 10:12:23\n$CM_INSTRUMENT JSM-7900F\n$CM_ACCEL_VOLT 5.00\n"
                                           "$CM_MAG 10000\n$CM_SIGNAL LED\n$SM_MICRON_BAR 128\n$SM_MICRON_MARKER 1um\n"
                                           "$$SM_SCAN_ROTATION 0\n")
    d = ns.load(p)
    assert d.metadata["instrument"]["model"] == "JSM-7900F" and d.metadata["beam"]["voltage_kV"] == 5
    assert d.pixel_size_nm == pytest.approx(1000 / 128)


def test_zeiss_tag(tmp_path):
    p = tmp_path / "zeiss.tif"
    text = "\x00\r\nAP_PIXEL_SIZE\r\nPixel Size = 5.581 nm\r\nAP_MAG\r\nMag = 20.00 K X\r\nAP_WD\r\nWD = 5.0 mm\r\n" \
           "AP_MANUALKV\r\nEHT = 3.00 kV\r\nDP_DETECTOR_CHANNEL\r\nSignal A = InLens\r\n"
    tifffile.imwrite(p, np.zeros((32, 32), np.uint8), extratags=[(34118, "s", 0, text, False)])
    d = ns.load(p)
    assert d.metadata["instrument"]["vendor"] == "Carl Zeiss" and d.metadata["optics"]["magnification"] == 20000
    assert d.metadata["beam"]["voltage_kV"] == 3 and d.metadata["optics"]["working_distance_mm"] == 5
    assert d.pixel_size_nm == pytest.approx(5.581) and d.metadata["detector"]["name"] == "InLens"


def test_rosettasciio_mrc(tmp_path):
    mrcfile = pytest.importorskip("mrcfile")
    p = tmp_path / "tomo.mrc"
    with mrcfile.new(p) as m:
        m.set_data(np.arange(4 * 8 * 8, dtype=np.float32).reshape(4, 8, 8))
        m.voxel_size = 2.5                                      # Å
    d = ns.load(p)
    assert d.shape == (4, 8, 8)
    assert d.provenance.activities[0].op.startswith("io.read.mrc")


# ------------------------------------------------------------------ round trips + provenance
@pytest.mark.parametrize("ext", [".nxs", ".zarr", ".tif"])
def test_round_trip_keeps_everything(tmp_path, ext):
    p = tmp_path / "quanta.tif"
    tifffile.imwrite(p, disks((48, 64)), extratags=[(34682, "s", 0, THERMO_INI, False)])
    d = an.denoise(ns.load(p), method="gaussian", strength=1.5)
    out = ns.save(d, tmp_path / f"out{ext}")
    r = ns.load(out)
    assert np.allclose(r.numpy(), d.numpy())
    assert r.pixel_size_nm == pytest.approx(12.4) and r.metadata["beam"]["voltage_kV"] == 5
    ops = [a.op for a in r.provenance.activities]
    assert ops[0] == "io.read.thermo" and "analyze.denoise" in ops and ops[-2].startswith("io.save")
    src = r.provenance.sources()[0]
    assert src.label == "quanta.tif" and len(src.sha256) == 64


def test_provenance_lineage_and_prov_json(tmp_path):
    d = ns.Dataset.from_array(disks(), pixel_size_nm=2.0, name="disks")
    f = an.fft(an.subtract_background(d, sigma_nm=100))
    p = f.provenance
    assert [a.op for a in p.activities] == ["create.from_array", "analyze.subtract_background", "analyze.fft"]
    assert p.activities[1].params["sigma_nm"] == 100
    assert p.activities[2].used == [p.activities[1].generated[0]]          # chained by content hash
    assert "nuscope" in p.activities[-1].software and "org:nuance" in p.agents
    doc = p.to_prov_json()
    assert len(doc["activity"]) == 3 and len(doc["used"]) == 2 and doc["wasAssociatedWith"]
    assert d.provenance.activities[-1].op == "create.from_array"            # input untouched


# ------------------------------------------------------------------ analysis in physical units
def test_particles_physical_units():
    r_px, ps = 20, 2.5
    d = ns.Dataset.from_array(disks(r=r_px), pixel_size_nm=ps)
    t = an.particles(d)
    assert len(t) == 3
    assert t.eq_diameter_nm.median() == pytest.approx(2 * r_px * ps, rel=0.06)
    assert t.circularity.median() > 0.85
    assert t.attrs["provenance"].activities[-1].op == "analyze.particles"


def test_fft_reciprocal_calibration_finds_period():
    ps, period_nm = 0.5, 4.0
    x = np.arange(256) * ps
    img = np.tile(np.sin(2 * np.pi * x / period_nm), (256, 1))
    d = ns.Dataset.from_array(img, pixel_size_nm=ps)
    f = an.fft(d, log=False)
    assert f.axes[-1].units == "1/nm"
    prof = an.radial_profile(f)
    peak = prof.loc[prof.intensity.idxmax()]
    assert peak.period == pytest.approx(period_nm, rel=0.05)


def test_line_profile_length_and_calibrate():
    d = ns.Dataset.from_array(np.zeros((50, 50)), pixel_size_nm=2.0)
    lp = an.line_profile(d, (10, 10), (10, 40))
    assert lp.distance.iloc[-1] == pytest.approx(60.0)
    c = an.calibrate(d, 1.0, reason="Au cross-grating 463 nm")
    assert c.pixel_size_nm == 1.0 and c.provenance.activities[-1].params["reason"].startswith("Au")


# ------------------------------------------------------------------ RO-Crate
def test_ro_crate(tmp_path):
    d = ns.Dataset.from_array(disks(), pixel_size_nm=2.0, name="sample_A")
    out = __import__("nuscope.crate", fromlist=["write_crate"]).write_crate(
        [an.denoise(d, method="median")], tmp_path / "crate", title="Disks test",
        authors=[{"name": "Roberto dos Reis", "orcid": "https://orcid.org/0000-0000-0000-0000"}])
    g = json.loads(out.read_text())["@graph"]
    types = {x["@type"] for x in g}
    assert {"Dataset", "File", "CreateAction", "Person", "Organization", "SoftwareApplication"} <= types
    root = next(x for x in g if x["@id"] == "./")
    assert root["hasPart"] == [{"@id": "sample_A.nxs"}] and (tmp_path / "crate" / "sample_A.nxs").exists()


# ------------------------------------------------------------------ Globus (mocked services)
CID = "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"


class FakeTransfer:
    def __init__(self, files):
        self.files = files
        self.submitted = []

    def operation_ls(self, collection, path="/", show_hidden=False):
        assert collection == CID
        base = path.rstrip("/")
        names = {}
        for full, data in self.files.items():
            if full.startswith(base + "/"):
                rest = full[len(base) + 1:]
                head = rest.split("/")[0]
                names[head] = ("dir", 0) if "/" in rest else ("file", len(data))
        return {"DATA": [{"name": n, "type": t, "size": s, "last_modified": "2026-10-13 10:00:00+00:00"}
                         for n, (t, s) in sorted(names.items())]}

    def get_endpoint(self, collection):
        return {"https_server": "https://g-1234.data.globus.org"}

    def submit_transfer(self, td):
        self.submitted.append(td)
        return {"task_id": "task-1"}


class FakeResponse:
    def __init__(self, data, status=200):
        self.data, self.status_code, self.content = data, status, data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def iter_content(self, n):
        for i in range(0, len(self.data), n):
            yield self.data[i:i + n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeHTTP:
    def __init__(self, files):
        self.files, self.calls = files, []

    def get(self, url, headers=None, stream=True, timeout=None):
        self.calls.append((url, headers))
        path = "/" + url.split(".org/", 1)[1]
        from urllib.parse import unquote
        return FakeResponse(self.files[unquote(path)])


def test_globus_load_ls_and_transfer(tmp_path):
    src = tmp_path / "src.tif"
    tifffile.imwrite(src, np.zeros((48, 64), np.uint8), extratags=[(34682, "s", 0, THERMO_INI, False)])
    files = {"/nuance/helios/run 1/img.tif": src.read_bytes(), "/nuance/helios/notes.txt": b"x"}
    s = GlobusSession(transfer_client=FakeTransfer(files), http=FakeHTTP(files), auth_header=lambda c: "Bearer TEST")
    assert [f.name for f in s.ls(CID, "/nuance/helios")] == ["notes.txt", "run 1"]
    assert [f.path for f in s.find(CID, "/nuance", "*.tif")] == ["/nuance/helios/run 1/img.tif"]
    url = f"globus://{CID}/nuance/helios/run 1/img.tif"
    assert parse_url(url) == (CID, "/nuance/helios/run 1/img.tif")
    d = ns.load(url, session=s, cache_dir=tmp_path / "cache")
    assert d.pixel_size_nm == pytest.approx(12.4)
    remote = [e for e in d.provenance.entities.values() if e.kind == "remote"]
    assert remote and remote[0].location == url and remote[0].attributes["globus_collection"] == CID
    assert remote[0].id in d.provenance.activities[0].used
    assert s.http.calls[0][1]["Authorization"] == "Bearer TEST" and "run%201" in s.http.calls[0][0]
    n_calls = len(s.http.calls)
    _, ent = fetch(url, session=s, cache_dir=tmp_path / "cache")      # cached: no second download
    assert len(s.http.calls) == n_calls and ent.attributes["from_cache"]
    pytest.importorskip("globus_sdk")
    tid = s.transfer_to(CID, "/nuance/helios", CID, "/backup/helios", recursive=True)
    assert tid == "task-1" and s.transfer.submitted[0]["DATA"][0]["recursive"] is True


def test_globus_requires_client_id(monkeypatch, tmp_path):
    pytest.importorskip("globus_sdk")
    monkeypatch.delenv("NUSCOPE_GLOBUS_CLIENT_ID", raising=False)
    monkeypatch.setattr("nuscope.globus.CONFIG", tmp_path / "none.json")
    from nuscope.globus import GlobusError
    with pytest.raises(GlobusError, match="client id"):
        GlobusSession().app


def test_cli_info_and_convert(tmp_path, capsys):
    from nuscope.cli import main
    p = tmp_path / "quanta.tif"
    tifffile.imwrite(p, np.zeros((48, 64), np.uint8), extratags=[(34682, "s", 0, THERMO_INI, False)])
    assert main(["info", str(p)]) == 0
    out = capsys.readouterr().out
    assert "Quanta FEG 650" in out and "5 kV" in out
    assert main(["convert", str(p), str(tmp_path / "q.nxs")]) == 0
    assert main(["provenance", str(tmp_path / "q.nxs"), "--prov-json", str(tmp_path / "p.json")]) == 0
    assert "io.read.thermo" in capsys.readouterr().out and (tmp_path / "p.json").exists()


def test_gatan_tag_mapping():
    from nuscope import metadata as md
    from nuscope.io.rsciio_backend import _gatan
    orig = {"ImageList": {"TagGroup0": {"ImageTags": {}}, "TagGroup1": {"ImageTags": {
        "Microscope Info": {"Voltage": 300000.0, "Indicated Magnification": 60000.0, "Illumination Mode": "STEM",
                            "Operation Mode": "SCANNING", "STEM Camera Length": 30.0, "Probe Current (nA)": 0.0},
        "DigiScan": {"Sample Time": 16.0, "Number Summing Frames": 5.0},
        "Session Info": {"Operator": "mb", "Specimen": "A12", "Microscope": []},
        "EELS": {"Experimental Conditions": {"Collection semi-angle (mrad)": 50.0, "Convergence semi-angle (mrad)": 21.0}},
        "GMS Version": {"Created": "3.60"}}}}}
    m = _gatan(orig, md.empty())
    assert m["technique"] == "STEM" and m["beam"]["voltage_kV"] == 300 and "current_nA" not in m["beam"]
    assert m["optics"] == {"magnification": 60000.0, "camera_length_mm": 30.0}
    assert m["acquisition"]["dwell_us"] == 16 and m["acquisition"]["operator"] == "mb" and m["sample"]["name"] == "A12"
    assert m["detector"]["collection_semiangle_mrad"] == 50 and m["detector"]["name"] == "EELS"
