"""The bundle self-test is a windowed exe: it must never raise, only report.

An unhandled exception would pop a traceback dialog and hang the build job
until the runner's timeout instead of failing it.
"""

from pathlib import Path

import pytest

from scorecap.cli import _selftest


@pytest.fixture(scope="module")
def report(tmp_path_factory, qapp):
    """One run for every question about it: it builds a PDF and a window."""
    path = tmp_path_factory.mktemp("selftest") / "selftest.txt"
    code = _selftest(path)
    return code, path.read_text(encoding="utf-8")


def test_a_working_build_reports_ok(report):
    code, text = report
    assert code == 0
    assert "RESULT: ok" in text
    assert "pdf:" in text
    assert "qt: window constructed" in text


def test_the_report_says_whether_velopack_sees_an_installation(report):
    # From the source tree there is no installation, and no update check may
    # reach out to the network - CI runs this very path.
    _, text = report
    assert "velopack: installed=False" in text
    assert "newest=" not in text


def test_an_unwritable_report_does_not_raise(qapp):
    # No dialog, no traceback: the exit code is the channel that matters.
    assert _selftest(Path("Z:/does-not-exist/scorecap/selftest.txt")) in (0, 1)


def test_a_broken_build_reports_the_failure(tmp_path, qapp, monkeypatch):
    import scorecap.pdf

    def explode(*args, **kwargs):
        raise RuntimeError("PyMuPDF data files missing")

    monkeypatch.setattr(scorecap.pdf, "build", explode)
    path = tmp_path / "selftest.txt"
    assert _selftest(path) == 1
    text = path.read_text(encoding="utf-8")
    assert "RESULT: failed" in text
    assert "PyMuPDF data files missing" in text
