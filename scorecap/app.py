"""Main window: captures on the left, the printed proof on the right."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QEvent, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QCursor, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import icons, pdf
from .capture import SelectionOverlay, grab
from .cropdialog import CropDialog
from .hotkey import HotkeyFilter
from .layout import paginate
from .model import Document, Shot, normalize_move
from .preview import PreviewWidget
from .settingsdialog import SettingsDialog, load_settings, save_settings
from .shotlist import ShotList, row_data
from .theme import Palette, palette_for, stylesheet, system_prefers_dark
from .trim import auto_crop

REBUILD_DELAY_MS = 150
TOAST_MS = 900
TOAST_MARGIN_PX = 8
TOAST_OFFSET_PX = 12
ZOOM_STEP = 1.25


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
        self.resize(1240, 880)

        self._store = QSettings("ScoreCap", "ScoreCap")
        self.settings = load_settings(self._store)
        self.palette_tokens: Palette = palette_for(system_prefers_dark())
        self.document = Document()
        self._pdf_bytes = b""
        self._temp_dir = Path(tempfile.mkdtemp(prefix="scorecap-"))
        self._pending_replace: int | None = None
        self._capturing = False
        self._dirty = False

        self._build_ui()
        self._build_capture_parts()
        self.setStyleSheet(stylesheet(self.palette_tokens))

    # --- construction ----------------------------------------------------

    def _button(self, text: str, glyph: str, name: str = "Quiet") -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(name)
        button.setProperty("glyph", glyph)
        self._apply_icon(button)
        return button

    def _apply_icon(self, button: QPushButton) -> None:
        if not icons.available():
            return
        primary = button.objectName() == "Primary"
        colour = self.palette_tokens.paper if primary else self.palette_tokens.text
        button.setIcon(icons.icon(button.property("glyph"), colour))

    def apply_palette(self, palette: Palette) -> None:
        """Switch theme: stylesheet, icon colours and the painted widgets."""
        self.palette_tokens = palette
        self.setStyleSheet(stylesheet(palette))
        for button in self.findChildren(QPushButton):
            if button.property("glyph"):
                self._apply_icon(button)
        self.shot_list.set_palette(palette)
        self.preview.set_palette(palette)
        self._toast.setStyleSheet(
            f"background: {palette.text}; color: {palette.app}; border-radius: 4px;"
        )

    def _build_ui(self) -> None:
        self.capture_button = self._button("Aufnahme vorbereiten", icons.CAPTURE, "Primary")
        self.capture_button.clicked.connect(self.arm_capture)
        self.capture_button.setToolTip(
            "Fenster tritt zur Seite; die Aufnahme startet erst mit dem Hotkey"
        )
        self.recapture_button = self._button("Neu aufnehmen", icons.RECAPTURE)
        self.recapture_button.clicked.connect(self.recapture_selected)
        self.crop_button = self._button("Zuschneiden", icons.CROP)
        self.crop_button.clicked.connect(self.crop_selected)
        self.delete_button = self._button("Löschen", icons.DELETE)
        self.delete_button.clicked.connect(self.delete_selected)
        self.settings_button = self._button("Einstellungen", icons.SETTINGS)
        self.settings_button.clicked.connect(self.edit_settings)

        toolbar = QWidget()
        toolbar.setObjectName("Toolbar")
        bar = QHBoxLayout(toolbar)
        bar.setContentsMargins(12, 8, 12, 8)
        bar.setSpacing(8)
        bar.addWidget(self.capture_button)
        bar.addSpacing(8)
        for button in (self.recapture_button, self.crop_button, self.delete_button):
            bar.addWidget(button)
        bar.addStretch(1)
        bar.addWidget(self.settings_button)

        self.shot_list = ShotList(self.palette_tokens)
        self.shot_list.model().rowsMoved.connect(self._on_rows_moved)
        self.shot_list.currentRowChanged.connect(self._update_actions)

        self.empty_state = QLabel(
            f"Noch nichts aufgenommen.\n\n{self.settings.hotkey} drücken, "
            "dann den Bereich aufziehen."
        )
        self.empty_state.setObjectName("EmptyState")
        self.empty_state.setAlignment(Qt.AlignCenter)
        self.empty_state.setWordWrap(True)

        self._list_stack = QStackedWidget()
        self._list_stack.addWidget(self.empty_state)
        self._list_stack.addWidget(self.shot_list)

        heading = QLabel("Aufnahmen")
        heading.setObjectName("Heading")

        side = QWidget()
        side.setObjectName("SidePanel")
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(12, 12, 12, 12)
        side_layout.setSpacing(8)
        side_layout.addWidget(heading)
        side_layout.addWidget(self._list_stack, 1)

        self.preview = PreviewWidget(self.palette_tokens)
        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)
        preview_layout.addWidget(self.preview, 1)
        preview_layout.addWidget(self._build_zoom_bar())

        splitter = QSplitter()
        splitter.addWidget(side)
        splitter.addWidget(preview_panel)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 920])

        self.status = QLabel("Noch keine Aufnahme")
        self.status.setObjectName("StatusText")
        self.export_button = self._button("Als PDF exportieren", icons.EXPORT, "Primary")
        self.export_button.clicked.connect(self.export)
        self.export_button.setEnabled(False)

        status_bar = QWidget()
        status_bar.setObjectName("StatusBar")
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(12, 8, 12, 8)
        status_layout.addWidget(self.status, 1)
        status_layout.addWidget(self.export_button)

        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(toolbar)
        root.addWidget(splitter, 1)
        root.addWidget(status_bar)
        container = QWidget()
        container.setLayout(root)
        self.setCentralWidget(container)

        undo_action = QAction("Rückgängig", self)
        undo_action.setShortcut(QKeySequence.Undo)
        undo_action.triggered.connect(self.undo)
        self.addAction(undo_action)
        self._update_actions()

    def _build_zoom_bar(self) -> QWidget:
        self.zoom_out_button = self._button("", icons.ZOOM_OUT)
        self.zoom_out_button.setToolTip("Verkleinern")
        self.zoom_out_button.clicked.connect(lambda: self._step_zoom(1 / ZOOM_STEP))
        self.zoom_in_button = self._button("", icons.ZOOM_IN)
        self.zoom_in_button.setToolTip("Vergrößern")
        self.zoom_in_button.clicked.connect(lambda: self._step_zoom(ZOOM_STEP))
        self.fit_button = self._button("Einpassen", icons.ZOOM_FIT)
        self.fit_button.setCheckable(True)
        self.fit_button.setChecked(True)
        self.fit_button.clicked.connect(self._fit_width)
        self.zoom_label = QLabel("100 %")
        self.zoom_label.setObjectName("Numeric")

        bar = QWidget()
        bar.setObjectName("ZoomBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(6)
        layout.addStretch(1)
        layout.addWidget(self.zoom_out_button)
        layout.addWidget(self.zoom_label)
        layout.addWidget(self.zoom_in_button)
        layout.addWidget(self.fit_button)
        return bar

    def _build_capture_parts(self) -> None:
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
            f"background: {self.palette_tokens.text};"
            f"color: {self.palette_tokens.app};"
            "border-radius: 4px;"
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
        self._update_zoom_label()
        self._dirty = False

    def _refresh_list(self, shots: Sequence[Shot], missing: set[int]) -> None:
        blocked = self.shot_list.blockSignals(True)
        current = self.shot_list.currentRow()
        self.shot_list.clear()
        for index, shot in enumerate(shots):
            self.shot_list.add_row(
                row_data(index, shot, self.settings, missing=index in missing)
            )
        if 0 <= current < self.shot_list.count():
            self.shot_list.setCurrentRow(current)
        self.shot_list.blockSignals(blocked)
        self._list_stack.setCurrentWidget(
            self.shot_list if shots else self.empty_state
        )
        self._update_actions()

    def _update_actions(self, *_args) -> None:
        has_selection = self.shot_list.currentRow() >= 0
        for button in (self.recapture_button, self.crop_button, self.delete_button):
            button.setEnabled(has_selection)

    def _update_zoom_label(self) -> None:
        self.zoom_label.setText(f"{round(self.preview.zoom * 100)} %")
        self.fit_button.setChecked(self.preview.fits_width)

    def _fit_width(self) -> None:
        self.preview.fit_to_width()
        self._update_zoom_label()

    def _step_zoom(self, factor: float) -> None:
        self.preview.set_zoom(self.preview.zoom * factor)
        self._update_zoom_label()

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
        dialog = CropDialog(self.document.shots[index], self, self.palette_tokens)
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
