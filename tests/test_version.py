"""The packaged app has no dist-info, so the version lives in the source."""

import re
import tomllib
from pathlib import Path

import scorecap
from scorecap._version import __version__

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_version_looks_like_a_release():
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?", __version__)


def test_pyproject_and_module_agree():
    declared = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]
    assert declared == __version__, (
        "pyproject.toml and scorecap/_version.py drifted apart; "
        "release-please must update both"
    )


def test_package_exposes_the_version():
    assert scorecap.__version__ == __version__


def test_release_please_marker_is_present():
    # Without the marker release-please silently stops bumping this file.
    source = (Path(scorecap.__file__).parent / "_version.py").read_text(encoding="utf-8")
    assert "x-release-please-version" in source
