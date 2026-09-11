"""The bundle self-test is a windowed exe: it must never raise, only report.

An unhandled exception would pop a traceback dialog and hang the build job
until the runner's timeout instead of failing it.
"""

from pathlib import Path

from scorecap.cli import _selftest


def test_a_working_build_reports_ok(tmp_path, qapp):
    report = tmp_path / "selftest.txt"
    assert _selftest(report) == 0
    text = report.read_text(encoding="utf-8")
    assert "RESULT: ok" in text
    assert "pdf:" in text
    assert "qt: window constructed" in text


def test_an_unwritable_report_does_not_raise(qapp):
    # No dialog, no traceback: the exit code is the channel that matters.
    unwritable = Path("Z:/does-not-exist/scorecap/selftest.txt")
    assert _selftest(unwritable) in (0, 1)


def test_a_broken_build_reports_the_failure(tmp_path, qapp, monkeypatch):
    import scorecap.pdf

    def explode(*args, **kwargs):
        raise RuntimeError("PyMuPDF data files missing")

    monkeypatch.setattr(scorecap.pdf, "build", explode)
    report = tmp_path / "selftest.txt"
    assert _selftest(report) == 1
    text = report.read_text(encoding="utf-8")
    assert "RESULT: failed" in text
    assert "PyMuPDF data files missing" in text
