"""Project files keep captures beyond a session - and never lose them."""

import json
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from scorecap.model import Shot
from scorecap.project import FORMAT_VERSION, load_project, save_project


def capture(tmp_path: Path, name: str, seed: int, crop=None) -> Shot:
    image = Image.new("RGB", (600, 180), "white")
    draw = ImageDraw.Draw(image)
    for line in range(5):
        draw.line([10, 40 + line * 12, 590, 40 + line * 12], fill="black", width=2)
    draw.ellipse([50 + seed * 30, 60, 70 + seed * 30, 74], fill="black")
    path = tmp_path / name
    image.save(path)
    return Shot(path=path, width=600, height=180, crop=crop)


def test_a_saved_project_opens_with_the_same_captures(tmp_path):
    shots = [
        capture(tmp_path, "a.png", 0),
        capture(tmp_path, "b.png", 1, crop=(20, 10, 500, 170)),
        capture(tmp_path, "c.png", 2),
    ]
    project = tmp_path / "Perseus.scorecap"
    save_project(project, shots)

    opened = load_project(project, tmp_path / "session")
    assert [(s.width, s.height, s.crop) for s in opened] == [
        (s.width, s.height, s.crop) for s in shots
    ]
    for original, restored in zip(shots, opened):
        with Image.open(original.path) as a, Image.open(restored.path) as b:
            assert a.tobytes() == b.convert(a.mode).tobytes()  # pixel for pixel
        assert restored.path.parent == tmp_path / "session"


def test_the_project_survives_the_session_files_being_deleted(tmp_path):
    shots = [capture(tmp_path, "a.png", 0)]
    project = tmp_path / "p.scorecap"
    save_project(project, shots)
    shots[0].path.unlink()  # what closing the app does to the session folder
    assert len(load_project(project, tmp_path / "session")) == 1


def test_a_failed_save_leaves_the_previous_file_intact(tmp_path):
    project = tmp_path / "p.scorecap"
    save_project(project, [capture(tmp_path, "a.png", 0)])
    before = project.read_bytes()

    gone = Shot(path=tmp_path / "missing.png", width=600, height=180)
    with pytest.raises(OSError):
        save_project(project, [capture(tmp_path, "b.png", 1), gone])

    assert project.read_bytes() == before
    assert not any(p.name.startswith("p.scorecap.") for p in tmp_path.iterdir())


def test_the_manifest_records_format_and_order(tmp_path):
    project = tmp_path / "p.scorecap"
    save_project(project, [capture(tmp_path, "a.png", 0), capture(tmp_path, "b.png", 1)])
    with zipfile.ZipFile(project) as archive:
        manifest = json.loads(archive.read("project.json"))
    assert manifest["format"] == FORMAT_VERSION
    assert [entry["file"] for entry in manifest["shots"]] == ["shots/001.png", "shots/002.png"]


def test_something_that_is_not_a_project_is_rejected(tmp_path):
    fake = tmp_path / "x.scorecap"
    fake.write_bytes(b"not a zip")
    with pytest.raises(ValueError):
        load_project(fake, tmp_path / "session")


def test_a_newer_format_is_refused_rather_than_misread(tmp_path):
    project = tmp_path / "new.scorecap"
    with zipfile.ZipFile(project, "w") as archive:
        archive.writestr("project.json", json.dumps({"format": FORMAT_VERSION + 1, "shots": []}))
    with pytest.raises(ValueError, match="newer"):
        load_project(project, tmp_path / "session")


def test_a_missing_capture_inside_the_project_is_reported(tmp_path):
    project = tmp_path / "broken.scorecap"
    manifest = {"format": FORMAT_VERSION, "shots": [
        {"file": "shots/001.png", "width": 10, "height": 10, "crop": None}
    ]}
    with zipfile.ZipFile(project, "w") as archive:
        archive.writestr("project.json", json.dumps(manifest))
    with pytest.raises(ValueError):
        load_project(project, tmp_path / "session")


def test_paths_inside_the_archive_cannot_escape_the_session_folder(tmp_path):
    # A crafted project must not write outside the folder it is unpacked to.
    project = tmp_path / "evil.scorecap"
    image = tmp_path / "i.png"
    Image.new("RGB", (10, 10), "white").save(image)
    manifest = {"format": FORMAT_VERSION, "shots": [
        {"file": "../../escaped.png", "width": 10, "height": 10, "crop": None}
    ]}
    with zipfile.ZipFile(project, "w") as archive:
        archive.writestr("project.json", json.dumps(manifest))
        archive.write(image, "../../escaped.png")
    session = tmp_path / "deep" / "session"
    try:
        opened = load_project(project, session)
    except ValueError:
        opened = []
    assert not (tmp_path / "escaped.png").exists()
    for shot in opened:
        assert shot.path.resolve().is_relative_to(session.resolve())


def test_scans_stay_scans_after_saving_and_opening(tmp_path):
    from dataclasses import replace

    shots = [capture(tmp_path, "a.png", 0), replace(capture(tmp_path, "b.png", 1), scan=True)]
    project = tmp_path / "p.scorecap"
    save_project(project, shots)
    assert [s.scan for s in load_project(project, tmp_path / "session")] == [False, True]


def test_projects_without_the_scan_flag_open_as_captures(tmp_path):
    project = tmp_path / "old.scorecap"
    save_project(project, [capture(tmp_path, "a.png", 0)])
    with zipfile.ZipFile(project) as archive:
        manifest = json.loads(archive.read("project.json"))
        image = archive.read("shots/001.png")
    for entry in manifest["shots"]:
        entry.pop("scan", None)
    with zipfile.ZipFile(project, "w") as archive:
        archive.writestr("project.json", json.dumps(manifest))
        archive.writestr("shots/001.png", image)
    (shot,) = load_project(project, tmp_path / "session")
    assert shot.scan is False


def test_erasures_survive_a_save_and_open(tmp_path):
    shot = capture(tmp_path, "a.png", 0, crop=(10, 10, 500, 170))
    shot = replace(shot, erasures=((100, 20, 140, 60), (300, 30, 320, 50)))
    project = tmp_path / "Perseus.scorecap"
    save_project(project, [shot])
    opened = load_project(project, tmp_path / "session")
    assert opened[0].erasures == ((100, 20, 140, 60), (300, 30, 320, 50))


def test_a_project_without_erasures_opens_with_none(tmp_path):
    """Projects written before the eraser existed stay readable."""
    project = tmp_path / "old.scorecap"
    save_project(project, [capture(tmp_path, "a.png", 0)])
    with zipfile.ZipFile(project) as archive:
        manifest = json.loads(archive.read("project.json"))
        data = {name: archive.read(name) for name in archive.namelist()}
    for entry in manifest["shots"]:
        entry.pop("erasures", None)
    stripped = tmp_path / "stripped.scorecap"
    with zipfile.ZipFile(stripped, "w") as archive:
        for name, payload in data.items():
            if name != "project.json":
                archive.writestr(name, payload)
        archive.writestr("project.json", json.dumps(manifest))
    assert load_project(stripped, tmp_path / "session").pop().erasures == ()
