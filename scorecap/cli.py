"""Application start-up: Velopack hand-off, window icon, self-test."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import logs
from ._version import __version__
from .app import MainWindow

log = logging.getLogger(__name__)


def _start_velopack() -> None:
    """Hand control to Velopack first so it can run install and update hooks.

    Called too late - after QApplication exists - an update would fail. Outside
    an installed bundle this does nothing, which is exactly what running from
    the source tree needs.
    """
    try:
        import velopack

        velopack.App().run()
        log.info("velopack hand-off done")
    except Exception as error:  # not installed, or velopack unavailable
        log.info("velopack hand-off skipped: %s", error)


def _icon_path() -> Path:
    """Find the icon in the source tree and in a PyInstaller bundle alike."""
    bundled = Path(getattr(sys, "_MEIPASS", "")) / "assets" / "scorecap.ico"
    if bundled.is_file():
        return bundled
    return Path(__file__).resolve().parent.parent / "assets" / "scorecap.ico"


def _write_report(report: Path, lines: list[str]) -> None:
    """Best effort: the exit code is the real channel, the file is a courtesy.

    A windowed executable turns an unhandled exception into a dialog, which
    would hang a build job rather than fail it.
    """
    try:
        with report.open("w", encoding="utf-8") as handle:
            for line in lines:
                print(line, file=handle)
    except OSError:
        pass


def _selftest(report: Path) -> int:
    """Prove a built bundle really works, not just that it opens a window.

    Exercises the parts a packaging mistake breaks first: PyMuPDF and Pillow
    data files, and the Qt platform plugins. Written to a file because a
    windowed executable has nowhere to print.
    """
    import os
    import tempfile

    lines: list[str] = [f"scorecap {__version__}"]
    try:
        from PIL import Image

        from .layout import paginate
        from .model import Shot
        from .pdf import build
        from .settings import Settings
        from .trim import auto_crop

        workdir = Path(tempfile.mkdtemp(prefix="scorecap-selftest-"))
        shots = []
        for index in range(3):
            path = workdir / f"{index}.png"
            image = Image.new("RGB", (1200, 300), (255, 255, 255))
            image.paste(Image.new("RGB", (900, 80), (20, 20, 20)), (150, 110))
            image.save(path)
            shots.append(auto_crop(Shot(path=path, width=1200, height=300), Settings()))
        pages = paginate([s.effective_size for s in shots], Settings())
        pdf_bytes = build(shots, pages, Settings())
        lines.append(f"pdf: {len(pages)} page(s), {len(pdf_bytes)} bytes")
        if not pdf_bytes.startswith(b"%PDF"):
            raise RuntimeError("output is not a PDF")

        # A scanned page with two staves: rendering, filters and ImageMath.
        from PIL import ImageDraw

        from .scan import import_scans

        page = Image.new("L", (1240, 1754), 235)
        draw = ImageDraw.Draw(page)
        for top in (300, 600):
            for line in range(5):
                draw.line([120, top + line * 12, 1120, top + line * 12], fill=20, width=2)
        scan_path = workdir / "scan.pdf"
        page.rotate(1.0, fillcolor=235).save(scan_path, resolution=150)
        imported = import_scans([scan_path], workdir)
        lines.append(f"scan: {len(imported.shots)} system(s) from {imported.pages} page(s)")
        if imported.errors or len(imported.shots) != 2:
            raise RuntimeError(f"scan import failed: {imported.errors}")

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication.instance() or QApplication(sys.argv[:1])
        from .app import MainWindow

        window = MainWindow()
        window.close()
        lines.append("qt: window constructed")

        # Makes an installed copy's update wiring observable from a script.
        # Only an installed copy asks GitHub; the build job must stay offline.
        from .updater import UpdateService

        updates = UpdateService()
        installed = updates.is_available()
        lines.append(
            f"velopack: installed={installed} current={updates.current_version()}"
        )
        if installed:
            pending = updates.check()
            newest = "up to date" if pending is None else pending.version
            lines.append(f"velopack: newest={newest}")
        lines.append("RESULT: ok")
        _write_report(report, lines)
        return 0
    except Exception as error:  # noqa: BLE001 - the report is the error channel
        import traceback

        lines.append(f"RESULT: failed: {error!r}")
        lines.append(traceback.format_exc())
        _write_report(report, lines)
        return 1


def main() -> int:
    if "--selftest" in sys.argv:
        index = sys.argv.index("--selftest")
        target = sys.argv[index + 1] if len(sys.argv) > index + 1 else "selftest.txt"
        return _selftest(Path(target))
    logs.configure(logs.log_path())
    if logs.console_requested():
        logs.configure_console()
    log.info("scorecap %s starting, argv=%s", __version__, sys.argv[1:])
    _start_velopack()
    app = QApplication(sys.argv)
    app.setApplicationName("ScoreCap")
    app.setApplicationVersion(__version__)
    icon = _icon_path()
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    window = MainWindow()
    window.install_hotkey(app)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
