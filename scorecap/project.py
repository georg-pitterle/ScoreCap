"""Save and open a session's captures as one .scorecap file.

A project is a ZIP archive: project.json lists the captures in order with
their crops, and shots/ holds each capture exactly as it was grabbed. Saving
writes to a sibling file first and swaps it in only when complete, so a
failure can never cost the previous version. Opening copies captures into the
session folder under names of its own choosing - nothing named inside the
archive decides where a file lands.
"""

from __future__ import annotations

import json
import os
import uuid
import zipfile
from pathlib import Path
from typing import Sequence

from ._version import __version__
from .model import Shot

FORMAT_VERSION = 1
SUFFIX = ".scorecap"
MANIFEST = "project.json"


def save_project(path: Path, shots: Sequence[Shot]) -> None:
    entries = []
    partial = path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.partial")
    try:
        # PNGs are compressed already; deflating them again only costs time.
        with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_STORED) as archive:
            for number, shot in enumerate(shots, start=1):
                name = f"shots/{number:03d}.png"
                archive.write(shot.path, name)  # OSError if a capture is gone
                entries.append(
                    {
                        "file": name,
                        "width": shot.width,
                        "height": shot.height,
                        "crop": list(shot.crop) if shot.crop else None,
                        "scan": shot.scan,
                    }
                )
            manifest = {"format": FORMAT_VERSION, "app": __version__, "shots": entries}
            archive.writestr(MANIFEST, json.dumps(manifest, indent=2))
        os.replace(partial, path)  # atomic on the same volume
    finally:
        partial.unlink(missing_ok=True)


def _read_manifest(archive: zipfile.ZipFile) -> dict:
    try:
        manifest = json.loads(archive.read(MANIFEST))
    except KeyError as error:
        raise ValueError("Die Datei ist kein ScoreCap-Projekt.") from error
    except json.JSONDecodeError as error:
        raise ValueError("Das Projekt ist beschädigt.") from error
    version = manifest.get("format")
    if not isinstance(version, int):
        raise ValueError("Das Projekt ist beschädigt.")
    if version > FORMAT_VERSION:
        raise ValueError(
            "Das Projekt stammt aus einer neueren ScoreCap-Version. "
            "Bitte ScoreCap aktualisieren."
        )
    return manifest


def load_project(path: Path, target_dir: Path) -> list[Shot]:
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as error:
        raise ValueError("Die Datei ist kein ScoreCap-Projekt.") from error
    with archive:
        manifest = _read_manifest(archive)
        target_dir.mkdir(parents=True, exist_ok=True)
        shots: list[Shot] = []
        for entry in manifest.get("shots", []):
            try:
                data = archive.read(entry["file"])
                crop = entry.get("crop")
                # Our own name, never one taken from the archive.
                target = target_dir / f"shot-{uuid.uuid4().hex}.png"
                target.write_bytes(data)
                shots.append(
                    Shot(
                        path=target,
                        width=int(entry["width"]),
                        height=int(entry["height"]),
                        crop=tuple(crop) if crop else None,
                        scan=bool(entry.get("scan", False)),
                    )
                )
            except (KeyError, TypeError) as error:
                raise ValueError("Im Projekt fehlt eine Aufnahme.") from error
            except ValueError as error:  # e.g. a crop outside the image
                raise ValueError("Das Projekt ist beschädigt.") from error
        return shots
