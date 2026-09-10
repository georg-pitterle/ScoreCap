"""Main window: shot list on the left, live PDF preview on the right."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QEvent, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QCursor, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from . import pdf
from .capture import SelectionOverlay, grab
from .cropdialog import CropDialog
from .hotkey import HotkeyFilter
from .layout import effective_dpi, paginate
from .model import Document, Shot, normalize_move
from .preview import PreviewWidget
from .settingsdialog import SettingsDialog, load_settings, save_settings
from .trim import auto_crop

REBUILD_DELAY_MS = 150
TOAST_MS = 900
TOAST_MARGIN_PX = 8
TOAST_OFFSET_PX = 12


def usable_shots(shots: Sequence[Shot]) -> tuple[list[Shot], list[int]]:
    """Split off shots whose file disappeared; they cannot be rendered."""
    usable: list[Shot] = []
    missing: list[int] = []
    for index, shot in enumerate(shots):
        if shot.path.exists():
            usable.append(shot)
        else:
            missing.append(index)
    return usable, missing


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ScoreCap")
        self.resize(1200, 850)

        self._store = QSettings("ScoreCap", "ScoreCap")
        self.settings = load_settings(self._store)
        self.document = Document()
        self._pdf_bytes = b""
        self._temp_dir = Path(tempfile.mkdtemp(prefix="scorecap-"))
        self._pending_replace: int | None = None
        self._capturing = False
        self._dirty = False

        self.shot_list = QListWidget()
        self.shot_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.shot_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.shot_list.model().rowsMoved.connect(self._on_rows_moved)

        self.preview = PreviewWidget()
        self.status = QLabel("Noch keine Aufnahme")

        capture_button = QPushButton("Aufnahme vorbereiten")
        capture_button.clicked.connect(self.arm_capture)
        recapture_button = QPushButton("Neu aufnehmen")
        recapture_button.clicked.connect(self.recapture_selected)
        crop_button = QPushButton("Zuschneiden")
        crop_button.clicked.connect(self.crop_selected)
        delete_button = QPushButton("Löschen")
        delete_button.clicked.connect(self.delete_selected)
        settings_button = QPushButton("Einstellungen")
        settings_button.clicked.connect(self.edit_settings)
        self.export_button = QPushButton("Als PDF exportieren")
        self.export_button.clicked.connect(self.export)
        self.export_button.setEnabled(False)

        left = QVBoxLayout()
        left.addWidget(capture_button)
        left.addWidget(self.shot_list, 1)
        for button in (recapture_button, crop_button, delete_button, settings_button):
            left.addWidget(button)
        left_panel = QWidget()
        left_panel.setLayout(left)

        splitter = QSplitter()
        splitter.addWidget(left_panel)
        splitter.addWidget(self.preview)
        splitter.setStretchFactor(1, 1)

        bottom = QHBoxLayout()
        bottom.addWidget(self.status, 1)
        bottom.addWidget(self.export_button)

        root = QVBoxLayout()
        root.addWidget(splitter, 1)
        root.addLayout(bottom)
        container = QWidget()
        container.setLayout(root)
        self.setCentralWidget(container)

        undo_action = QAction("Rückgängig", self)
        undo_action.setShortcut(QKeySequence.Undo)
        undo_action.triggered.connect(self.undo)
        self.addAction(undo_action)

        self._overlay = SelectionOverlay()
        self._overlay.selected.connect(self._on_selected)
        self._overlay.cancelled.connect(self.finish_capture)

        # Tool tip windows never take the focus, so the browser keeps it.
        # Parented to the window so Qt owns its lifetime; the flags still make
        # it a separate, focus-free window.
        self._toast = QLabel(
            self,
            Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus,
        )
        self._toast.setMargin(TOAST_MARGIN_PX)
        self._toast.setStyleSheet(
            "background: #202020; color: white; border-radius: 4px;"
        )
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.setInterval(TOAST_MS)
        self._toast_timer.timeout.connect(self._toast.hide)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(REBUILD_DELAY_MS)
        self._timer.timeout.connect(self.rebuild)

        self._hotkey = HotkeyFilter(self.begin_capture)

    # --- state -----------------------------------------------------------

    @property
    def pdf_bytes(self) -> bytes:
        return self._pdf_bytes

    @property
    def is_armed(self) -> bool:
        """True while the window waits out of the way for the hotkey."""
        return self._capturing

    @property
    def is_dirty(self) -> bool:
        """True when shots changed but the preview has not caught up yet."""
        return self._dirty

    def install_hotkey(self, app) -> None:
        app.installNativeEventFilter(self._hotkey)
        if not self._hotkey.register(self.settings.hotkey):
            QMessageBox.warning(
                self,
                "Hotkey belegt",
                f"Der Hotkey {self.settings.hotkey} ist bereits vergeben. "
                "Er lässt sich in den Einstellungen ändern.",
            )

    def schedule_rebuild(self) -> None:
        self._timer.start()

    def rebuild(self) -> None:
        if self._capturing:
            # Mid-series: only remember that work is pending. Rendering every
            # page after every shot would slow the capture loop down.
            self._dirty = True
            return
        shots = self.document.shots
        usable, missing = usable_shots(shots)
        pages = paginate([s.effective_size for s in usable], self.settings)
        self._pdf_bytes = pdf.build(usable, pages, self.settings)
        self.preview.set_pdf(self._pdf_bytes)
        self.export_button.setEnabled(bool(pages))
        self._refresh_list(shots, set(missing))
        text = f"{len(shots)} Aufnahmen, {len(pages)} Seiten"
        if missing:
            text += f", {len(missing)} Datei(en) fehlen"
        self.status.setText(text)
        self._dirty = False

    def _refresh_list(self, shots: Sequence[Shot], missing: set[int]) -> None:
        blocked = self.shot_list.blockSignals(True)
        current = self.shot_list.currentRow()
        self.shot_list.clear()
        for index, shot in enumerate(shots):
            width, height = shot.effective_size
            label = f"{index + 1}. {width}x{height} px"
            item = QListWidgetItem(label)
            if index in missing:
                item.setText(f"{label} — Datei fehlt")
                item.setForeground(Qt.red)
            elif effective_dpi(shot.effective_size, self.settings) < self.settings.min_dpi:
                item.setText(f"{label} — niedrige Druckqualität")
                item.setForeground(Qt.darkYellow)
            self.shot_list.addItem(item)
        if 0 <= current < self.shot_list.count():
            self.shot_list.setCurrentRow(current)
        self.shot_list.blockSignals(blocked)

    # --- actions ---------------------------------------------------------

    def add_shot(self, shot: Shot) -> None:
        self.document.add(shot)
        self.rebuild()

    def arm_capture(self) -> None:
        """Step aside and wait for the hotkey.

        The button only gets out of the way; opening the overlay right here
        would freeze the screen before the user has scrolled to the passage
        they want.
        """
        self._pending_replace = None
        self._arm()

    def recapture_selected(self) -> None:
        index = self.shot_list.currentRow()
        if index < 0:
            return
        self._pending_replace = index
        self._arm()

    def _arm(self) -> None:
        self._capturing = True
        self.showMinimized()
        self._hint(f"Bereit — {self.settings.hotkey} drücken")

    def begin_capture(self) -> None:
        """What the hotkey does: dim the screen and let the user drag."""
        self._capturing = True
        if not self.isMinimized():
            self.showMinimized()
        self._toast.hide()
        self._overlay.start()

    def finish_capture(self) -> None:
        """Leave capture mode: show the window again and catch up on rendering."""
        self._capturing = False
        self._pending_replace = None
        self._toast.hide()
        self.showNormal()
        self.raise_()
        self.activateWindow()
        if self._dirty:
            self.rebuild()

    def _on_selected(self, rect) -> None:
        shot = auto_crop(grab(rect, self._temp_dir), self.settings)
        replacing = self._pending_replace is not None
        if replacing:
            self.document.replace_shot(self._pending_replace, shot)
            self._pending_replace = None
        else:
            self.document.add(shot)
        self._dirty = True
        if replacing:
            # Replacing one shot is a deliberate edit - show the result.
            self.finish_capture()
            return
        # Stay minimised so the browser keeps the focus and the next hotkey
        # press works right away. Rendering waits until capturing is done.
        self._show_toast(rect, f"Aufnahme {len(self.document.shots)}")

    def changeEvent(self, event) -> None:  # noqa: N802
        # Restoring from the taskbar also ends a capture series, so the
        # preview never shows a stale document.
        if (
            event.type() == QEvent.WindowStateChange
            and self._capturing
            and not self.isMinimized()
        ):
            self.finish_capture()
        super().changeEvent(event)

    def _show_toast(self, rect, text: str) -> None:
        self._place_toast(text, rect.left(), rect.bottom() + TOAST_OFFSET_PX)
        self._toast_timer.start()

    def _hint(self, text: str) -> None:
        """A hint that stays put - it tells the user what to press next."""
        self._toast_timer.stop()
        cursor = QCursor.pos()
        self._place_toast(text, cursor.x() + TOAST_OFFSET_PX, cursor.y() + TOAST_OFFSET_PX)

    def _place_toast(self, text: str, x: int, y: int) -> None:
        self._toast.setText(text)
        self._toast.adjustSize()
        self._toast.move(x, y)
        self._toast.show()

    def crop_selected(self) -> None:
        index = self.shot_list.currentRow()
        if index < 0:
            return
        dialog = CropDialog(self.document.shots[index], self)
        if dialog.exec():
            self.document.set_crop(index, dialog.crop)
            self.rebuild()

    def delete_selected(self) -> None:
        index = self.shot_list.currentRow()
        if index < 0:
            return
        self.document.remove(index)
        self.rebuild()

    def undo(self) -> None:
        if self.document.undo():
            self.rebuild()

    def _on_rows_moved(self, parent, start, end, destination, row) -> None:
        self.document.move(start, normalize_move(start, row))
        self.schedule_rebuild()

    def edit_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if not dialog.exec():
            return
        previous_hotkey = self.settings.hotkey
        self.settings = dialog.settings
        save_settings(self.settings, self._store)
        if self.settings.hotkey != previous_hotkey:
            self._hotkey.register(self.settings.hotkey)
        self.rebuild()

    def export_to(self, path: Path) -> None:
        path.write_bytes(self._pdf_bytes)

    def export(self) -> None:
        name, _ = QFileDialog.getSaveFileName(
            self, "Als PDF speichern", "noten.pdf", "PDF (*.pdf)"
        )
        if not name:
            return
        try:
            self.export_to(Path(name))
        except OSError as error:
            QMessageBox.critical(self, "Export fehlgeschlagen", str(error))
        else:
            self.status.setText(f"Exportiert: {name}")

    def closeEvent(self, event) -> None:  # noqa: N802
        # The overlay is deliberately parentless (a child window would be
        # hidden along with the minimised main window), so close it by hand.
        self._overlay.hide()
        self._overlay.deleteLater()
        self._toast.hide()
        self._hotkey.unregister()
        for file in self._temp_dir.glob("*.png"):
            file.unlink(missing_ok=True)
        self._temp_dir.rmdir()
        super().closeEvent(event)
