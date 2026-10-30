"""Main window: captures on the left, the printed proof on the right."""

from __future__ import annotations

import logging
import shutil
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Sequence

from PIL import Image
from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QItemSelectionModel,
    QLocale,
    QSettings,
    QStandardPaths,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
)
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import icons, omr, pdf, reader
from .capture import SelectionOverlay, grab
from .cropdialog import MODES as EDIT_MODES
from .cropdialog import CropDialog
from .elided import ElidedLabel
from .hotkey import RETAKE_HOTKEY_ID, HotkeyFilter
from .layout import Page, paginate, placement_at
from .optimize import OptimizeResult, optimize_pdf
from .model import Document, PageSource, Shot, shifted_order
from .preview import PreviewWidget
from .project import SUFFIX, load_project, save_project
from .projectui import ask_save_changes, ask_stop_transcription, project_filter
from .scan import SUFFIXES as SCAN_SUFFIXES
from .scan import ImportResult
from .seriesbar import SeriesBar
from .settingsdialog import SettingsDialog, load_settings, save_settings
from .shotlist import ShotList, row_data
from .staff import staff_extent_of
from .tasks import (
    ClaudeExport,
    MusicXmlExport,
    MusicXmlSignals,
    BackgroundTask,
    ScanImport,
    ScanSignals,
    UpdateCheck,
    UpdateDownload,
    UpdateSignals,
)
from .theme import Palette, palette_for, stylesheet, system_prefers_dark
from .trim import auto_crop, crop_after_erasing
from .updater import PendingUpdate, UpdateService

REBUILD_DELAY_MS = 150
# Not Ctrl+Shift+S for "save as": that is the global capture hotkey.
SAVE_AS_KEY = "F12"
EDIT_KEY = "F2"
RECAPTURE_KEY = "Ctrl+R"
EXPORT_KEY = "Ctrl+E"
FIT_KEY = "Ctrl+0"
CLOSE_WAIT_S = 10.0
PROGRESS_WIDTH_PX = 160
ZOOM_STEP = 1.25
UPDATE_CHECK_DELAY_MS = 2000

log = logging.getLogger(__name__)


def settings_store() -> QSettings:
    """Where settings and remembered folders live: the user's registry."""
    return QSettings("ScoreCap", "ScoreCap")


def claude_work_root() -> Path:
    """Where Claude's readings work, kept across sessions.

    Not the session's temporary folder: a reading the usage limit stopped
    is taken up hours later, maybe after a restart, and only from the
    folder it began in.
    """
    local = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
    return Path(local) / "claude"


def scan_files(paths: Sequence[Path]) -> list[Path]:
    """The paths a scan import can read, by their suffix."""
    return [path for path in paths if path.suffix.lower() in SCAN_SUFFIXES]


def _shortcut_text(key: QKeySequence.StandardKey | str) -> str:
    """A shortcut as the user's language writes it, e.g. Strg+O."""
    return QKeySequence(key).toString(QKeySequence.SequenceFormat.NativeText)


def shrunk_name(source: Path) -> Path:
    """Where a shrunk copy goes by default: beside the original, never over it."""
    suffix = QCoreApplication.translate("MainWindow", "-small")
    return source.with_name(f"{source.stem}{suffix}{source.suffix}")


def _megabytes(size: int) -> str:
    return QLocale().toString(size / 1024 / 1024, "f", 1) + " MB"


@dataclass(frozen=True)
class Usable:
    """The shots that can be rendered, and where they sit in the document."""

    shots: list[Shot]
    rows: list[int]     # the document row each shot above came from
    missing: list[int]  # the rows whose file disappeared


def usable_shots(shots: Sequence[Shot]) -> Usable:
    """Split off shots whose file disappeared; they cannot be rendered."""
    kept: list[Shot] = []
    rows: list[int] = []
    missing: list[int] = []
    for index, shot in enumerate(shots):
        if shot.path.exists():
            kept.append(shot)
            rows.append(index)
        else:
            missing.append(index)
    return Usable(shots=kept, rows=rows, missing=missing)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ScoreCap")
        self.resize(1240, 880)

        self._store = settings_store()
        self.settings = load_settings(self._store)
        self.palette_tokens: Palette = palette_for(system_prefers_dark())
        self.document = Document()
        self._pdf_bytes = b""
        # The laid-out pages behind the preview, and which list row each
        # capture on them belongs to - the preview leaves missing files out.
        self._pages: list[Page] = []
        self._usable_rows: list[int] = []
        self._temp_dir = Path(tempfile.mkdtemp(prefix="scorecap-"))
        # Which page each imported system was cut from. Not saved: a project
        # keeps captures, not the scans behind them.
        self._scan_sources: dict[Path, PageSource] = {}
        self._pending_replace: int | None = None
        self._scan_task: ScanImport | None = None
        self._musicxml_task: MusicXmlExport | ClaudeExport | None = None
        # What Claude's reading has used so far; None while Audiveris reads.
        self._claude_usage: reader.Usage | None = None
        self._claude_reached: reader.Progress | None = None
        self._capturing = False
        self._series_taken = 0
        # The last thing exported: it stays in the status line, however often
        # the captures change, until there is a newer one to report.
        self._result = ""
        self._result_path: Path | None = None
        self._project_path: Path | None = None
        self._saved_revision = self.document.revision
        self._dirty = False

        self._build_ui()
        self._build_capture_parts()
        self.setStyleSheet(stylesheet(self.palette_tokens))
        self.setAcceptDrops(True)

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
        tokens = self.palette_tokens
        primary = button.objectName() == "Primary"
        colour = tokens.on_accent if primary else tokens.text
        button.setIcon(
            icons.icon(button.property("glyph"), colour, disabled=tokens.text_muted)
        )

    def _icon_button(self, glyph: str, name: str) -> QPushButton:
        """A button that only shows an icon, and says its name to a screen reader."""
        button = self._button("", glyph)
        button.setAccessibleName(name)
        return button

    def apply_palette(self, palette: Palette) -> None:
        """Switch theme: stylesheet, icon colours and the painted widgets."""
        self.palette_tokens = palette
        self.setStyleSheet(stylesheet(palette))
        for button in self.findChildren(QPushButton):
            if button.property("glyph"):
                self._apply_icon(button)
        # The preview takes its colours from the stylesheet above.
        self.shot_list.set_palette(palette)
        self._series_bar.set_palette(palette)

    def _follow_colour_scheme(self, scheme) -> None:
        """Windows switched between its light and dark app colours."""
        self.apply_palette(palette_for(scheme == Qt.ColorScheme.Dark))

    def _build_ui(self) -> None:
        self.capture_button = self._button("", icons.CAPTURE, "Primary")
        self.capture_button.clicked.connect(self.arm_capture)
        self.scan_button = self._button(self.tr("Import scans …"), icons.SCAN)
        self.scan_button.setToolTip(
            self.tr(
                "Clean up scanned pages (PDF or images) and split them into systems; "
                "files can also be dropped onto the window"
            )
        )
        self.scan_button.clicked.connect(self.choose_scans)
        self.undo_button = self._icon_button(icons.UNDO, self.tr("Undo"))
        self.undo_button.setToolTip(
            self.tr("Undo the last change ({shortcut})").format(
                shortcut=_shortcut_text(QKeySequence.Undo)
            )
        )
        self.undo_button.clicked.connect(self.undo)
        self.redo_button = self._icon_button(icons.REDO, self.tr("Redo"))
        self.redo_button.setToolTip(
            self.tr("Bring back what was undone ({shortcut})").format(
                shortcut=_shortcut_text(QKeySequence.Redo)
            )
        )
        self.redo_button.clicked.connect(self.redo)
        self.recapture_button = self._icon_button(
            icons.RECAPTURE, self.tr("Recapture")
        )
        self.recapture_button.setToolTip(
            self.tr(
                "Capture this line again; the new one replaces it ({shortcut})"
            ).format(shortcut=_shortcut_text(RECAPTURE_KEY))
        )
        self.recapture_button.clicked.connect(self.recapture_selected)
        self.edit_button = self._icon_button(icons.EDIT, self.tr("Edit"))
        self.edit_button.setToolTip(
            self.tr("Crop the capture or erase what disturbs ({shortcut})").format(
                shortcut=EDIT_KEY
            )
        )
        self.edit_button.clicked.connect(self.edit_selected)
        self.delete_button = self._icon_button(icons.DELETE, self.tr("Delete"))
        self.delete_button.setToolTip(self.tr("Delete this capture (Del)"))
        self.delete_button.clicked.connect(self.delete_selected)
        self.open_button = self._button(self.tr("Open …"), icons.OPEN)
        self.open_button.setToolTip(
            self.tr("Open a saved project ({shortcut})").format(
                shortcut=_shortcut_text(QKeySequence.Open)
            )
        )
        self.open_button.clicked.connect(self.open_project)
        self.save_button = self._button(self.tr("Save"), icons.SAVE)
        self.save_button.setToolTip(
            self.tr("Save the captures as a project ({save}, save as: {save_as})").format(
                save=_shortcut_text(QKeySequence.Save), save_as=SAVE_AS_KEY
            )
        )
        self.save_button.clicked.connect(self.save)
        self.extras_button = self._button(self.tr("Extras"), icons.MORE)
        extras_menu = QMenu(self.extras_button)
        # Not with the exports: it opens some other PDF, not this document.
        self.shrink_action = extras_menu.addAction(self.tr("Shrink a PDF file …"))
        self.shrink_action.setToolTip(
            self.tr("Shrink an existing PDF; the original stays unchanged")
        )
        self.shrink_action.triggered.connect(self.shrink_pdf)
        self.settings_action = extras_menu.addAction(self.tr("Settings …"))
        self.settings_action.triggered.connect(self.edit_settings)
        extras_menu.setToolTipsVisible(True)
        self.extras_button.setMenu(extras_menu)
        self.extras_button.setProperty("menu", True)
        self.musicxml_button = self._button(
            self.tr("Export as MusicXML …"), icons.MUSICXML
        )
        self.musicxml_button.setEnabled(False)
        self.musicxml_button.setToolTip(
            self.tr("Transcribe the score, for playing it back elsewhere")
        )
        musicxml_menu = QMenu(self.musicxml_button)
        # Before the choice, not in the README: a system cut in two at the
        # start costs every voice of the file.
        first_check = musicxml_menu.addAction(
            self.tr("Takes minutes. Check that no system is cut in two first.")
        )
        first_check.setEnabled(False)
        musicxml_menu.addSeparator()
        audiveris_action = musicxml_menu.addAction(self.tr("With Audiveris …"))
        audiveris_action.setToolTip(
            self.tr(
                "Free and offline; reads clean engraving well, about 15 seconds a page"
            )
        )
        audiveris_action.triggered.connect(lambda: self.export_musicxml("audiveris"))
        claude_action = musicxml_menu.addAction(
            self.tr("With Claude, one line per voice …")
        )
        claude_action.setToolTip(
            self.tr(
                "Claude Code reads the score and splits divided voices into "
                "lines for rehearsal files; takes minutes and counts towards "
                "your Claude plan"
            )
        )
        claude_action.triggered.connect(lambda: self.export_musicxml("claude"))
        musicxml_menu.setToolTipsVisible(True)
        self.musicxml_button.setMenu(musicxml_menu)
        self.musicxml_button.setProperty("menu", True)

        toolbar = QWidget()
        toolbar.setObjectName("Toolbar")
        bar = QHBoxLayout(toolbar)
        bar.setContentsMargins(12, 8, 12, 8)
        bar.setSpacing(8)
        bar.addWidget(self.capture_button)
        bar.addWidget(self.scan_button)
        bar.addStretch(1)
        bar.addWidget(self.open_button)
        bar.addWidget(self.save_button)
        bar.addWidget(self.extras_button)

        self.shot_list = ShotList(self.palette_tokens)
        self.shot_list.model().rowsMoved.connect(self._on_rows_moved)
        self.shot_list.currentRowChanged.connect(self._on_row_changed)
        self.shot_list.itemSelectionChanged.connect(self._on_row_changed)
        self.shot_list.itemDoubleClicked.connect(self._edit_item)
        self.shot_list.edit_requested.connect(self.edit_selected)
        self.shot_list.delete_requested.connect(self.delete_selected)
        self.shot_list.shift_requested.connect(self.shift_selected)

        self.empty_state = QLabel(self.tr("Nothing captured yet."))
        self.empty_state.setObjectName("EmptyState")
        self.empty_state.setAlignment(Qt.AlignCenter)
        self.empty_state.setWordWrap(True)

        self._list_stack = QStackedWidget()
        self._list_stack.addWidget(self.empty_state)
        self._list_stack.addWidget(self.shot_list)

        heading = QLabel(self.tr("Captures"))
        heading.setObjectName("Heading")
        # What acts on a row sits with the rows, not in the window's toolbar.
        header = QHBoxLayout()
        header.setSpacing(4)
        header.addWidget(heading)
        header.addStretch(1)
        for button in (
            self.undo_button,
            self.redo_button,
            self.recapture_button,
            self.edit_button,
            self.delete_button,
        ):
            header.addWidget(button)

        side = QWidget()
        side.setObjectName("SidePanel")
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(12, 12, 12, 12)
        side_layout.setSpacing(8)
        side_layout.addLayout(header)
        side_layout.addWidget(self._list_stack, 1)

        self.preview = PreviewWidget()
        self.preview.clicked_at.connect(self.select_at)
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

        self.status = ElidedLabel(self.tr("No capture yet"))
        self.status.setObjectName("StatusText")
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedWidth(PROGRESS_WIDTH_PX)
        self.progress_bar.hide()
        self.cancel_button = self._button(self.tr("Cancel"), icons.CANCEL)
        self.cancel_button.setToolTip(self.tr("Stop the transcription"))
        self.cancel_button.clicked.connect(self.cancel_transcription)
        self.cancel_button.hide()
        self.update_label = ElidedLabel()
        self.update_label.setObjectName("StatusText")
        self.update_label.hide()
        self.update_button = self._button(self.tr("Restart now"), icons.RECAPTURE)
        self.update_button.clicked.connect(self._restart_into_update)
        self.update_button.hide()
        self.result_button = self._button(self.tr("Open"), icons.RESULT)
        self.result_button.clicked.connect(self.open_result)
        self.result_button.hide()
        self.export_button = self._button(self.tr("Export as PDF"), icons.EXPORT, "Primary")
        self.export_button.setToolTip(
            self.tr("Save the pages as they stand here ({shortcut})").format(
                shortcut=_shortcut_text(EXPORT_KEY)
            )
        )
        self.export_button.clicked.connect(self.export)
        self.export_button.setEnabled(False)

        status_bar = QWidget()
        status_bar.setObjectName("StatusBar")
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(12, 8, 12, 8)
        status_layout.addWidget(self.status, 1)
        status_layout.addWidget(self.progress_bar)
        status_layout.addWidget(self.cancel_button)
        status_layout.addWidget(self.update_label)
        status_layout.addWidget(self.update_button)
        status_layout.addWidget(self.result_button)
        status_layout.addWidget(self.musicxml_button)
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

        # Not Ctrl+Shift+S for "save as": that is the global capture hotkey.
        for label, keys, slot in (
            (self.tr("Undo"), QKeySequence.Undo, self.undo),
            (self.tr("Redo"), QKeySequence.Redo, self.redo),
            (self.tr("Open"), QKeySequence.Open, self.open_project),
            (self.tr("Save"), QKeySequence.Save, self.save),
            (self.tr("Save as"), QKeySequence(SAVE_AS_KEY), self.save_as),
            (
                self.tr("Recapture"),
                QKeySequence(RECAPTURE_KEY),
                self.recapture_selected,
            ),
            (self.tr("Edit"), QKeySequence(EDIT_KEY), self.edit_selected),
            (self.tr("Export as PDF"), QKeySequence(EXPORT_KEY), self.export),
            (
                self.tr("Zoom in"),
                QKeySequence.ZoomIn,
                lambda: self._step_zoom(ZOOM_STEP),
            ),
            (
                self.tr("Zoom out"),
                QKeySequence.ZoomOut,
                lambda: self._step_zoom(1 / ZOOM_STEP),
            ),
            (self.tr("Fit width"), QKeySequence(FIT_KEY), self._fit_width),
        ):
            action = QAction(label, self)
            action.setShortcut(keys)
            action.triggered.connect(slot)
            self.addAction(action)
            if slot == self.export:
                self.export_action = action  # no pages, nothing to export
                action.setEnabled(False)
        self._show_hotkey()
        # Qt tabs through widgets in the order they were made, and the toolbar
        # and the panels were not made in the order they are read.
        chain = [
            self.capture_button,
            self.scan_button,
            self.open_button,
            self.save_button,
            self.extras_button,
            self.undo_button,
            self.redo_button,
            self.recapture_button,
            self.edit_button,
            self.delete_button,
            self.shot_list,
            self.preview,
            self.zoom_out_button,
            self.zoom_in_button,
            self.fit_button,
            self.cancel_button,
            self.update_button,
            self.result_button,
            self.musicxml_button,
            self.export_button,
        ]
        for before, after in zip(chain, chain[1:]):
            QWidget.setTabOrder(before, after)
        self._update_title()
        self._update_actions()

    def _hotkey_text(self) -> str:
        return _shortcut_text(self.settings.hotkey) or self.settings.hotkey

    def _show_hotkey(self) -> None:
        """Everywhere the window names the capture hotkey."""
        hotkey = self._hotkey_text()
        self.capture_button.setText(
            self.tr("Start series ({hotkey})").format(hotkey=hotkey)
        )
        self.capture_button.setToolTip(
            self.tr(
                "The window steps aside. Scroll to the passage, press {hotkey} "
                "and drag; capturing starts only with the hotkey"
            ).format(hotkey=hotkey)
        )
        self.preview.set_blank_text(
            self.tr(
                "Nothing here yet.\n\nStart a series, scroll to the passage, "
                "press {hotkey} and drag out each system. Every capture lands "
                "on this page, as it will print.\n\nOr drop scanned pages "
                "onto this window."
            ).format(hotkey=hotkey)
        )

    def _build_zoom_bar(self) -> QWidget:
        self.zoom_out_button = self._icon_button(icons.ZOOM_OUT, self.tr("Zoom out"))
        self.zoom_out_button.setToolTip(
            self.tr("Zoom out ({shortcut})").format(
                shortcut=_shortcut_text(QKeySequence.ZoomOut)
            )
        )
        self.zoom_out_button.clicked.connect(lambda: self._step_zoom(1 / ZOOM_STEP))
        self.zoom_in_button = self._icon_button(icons.ZOOM_IN, self.tr("Zoom in"))
        self.zoom_in_button.setToolTip(
            self.tr("Zoom in ({shortcut})").format(
                shortcut=_shortcut_text(QKeySequence.ZoomIn)
            )
        )
        self.zoom_in_button.clicked.connect(lambda: self._step_zoom(ZOOM_STEP))
        self.fit_button = self._button(self.tr("Fit width"), icons.ZOOM_FIT)
        self.fit_button.setToolTip(
            self.tr("Fit the page to the window's width ({shortcut})").format(
                shortcut=_shortcut_text(FIT_KEY)
            )
        )
        self.fit_button.setCheckable(True)
        self.fit_button.setChecked(True)
        self.fit_button.clicked.connect(self._fit_width)
        self.zoom_label = QLabel("100 %")
        self.zoom_label.setObjectName("Numeric")

        bar = QWidget()
        bar.setObjectName("ZoomBar")
        bar.setEnabled(False)  # nothing to zoom until there is a page
        self._zoom_bar = bar
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
        self._overlay.missed.connect(self._on_missed)
        self._overlay.retake.connect(self.retake_capture)
        self._series_bar = SeriesBar(self.palette_tokens)
        self._series_bar.retake_requested.connect(self.retake_capture)
        self._series_bar.undo_requested.connect(self._undo_in_series)
        self._series_bar.done_requested.connect(self.finish_capture)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(REBUILD_DELAY_MS)
        self._timer.timeout.connect(self.rebuild)

        self._hotkey = HotkeyFilter(self.begin_capture)
        self._retake_hotkey = HotkeyFilter(self.retake_capture, RETAKE_HOTKEY_ID)
        self._hotkeys_installed = False

        hints = QGuiApplication.styleHints()
        hints.colorSchemeChanged.connect(self._follow_colour_scheme)

        self.updates = UpdateService()
        self._ready_update: PendingUpdate | None = None
        self._restarting = False
        # Keeps each background task's wrapper alive until it has reported.
        self._running_tasks: set[BackgroundTask] = set()
        # Deferred so the first capture is never waiting on a network call.
        QTimer.singleShot(UPDATE_CHECK_DELAY_MS, self.check_for_updates)

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
        app.installNativeEventFilter(self._retake_hotkey)
        self._hotkeys_installed = True
        self._register_hotkey()

    def _register_hotkey(self) -> None:
        """Take the global hotkey, and say so when it cannot be had.

        A hotkey saved by an older version, or typed into the settings, may
        no longer parse - which must not cost the user the whole window.
        """
        try:
            if self._hotkey.register(self.settings.hotkey):
                return
            message = self.tr(
                "The hotkey {hotkey} is already in use. "
                "It can be changed in the settings."
            )
        except ValueError as error:
            log.info("hotkey %r not usable: %s", self.settings.hotkey, error)
            message = self.tr(
                "{hotkey} is not a usable hotkey. It can be changed in the settings."
            )
        QMessageBox.warning(
            self,
            self.tr("Hotkey unavailable"),
            message.format(hotkey=self.settings.hotkey),
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
        ready = usable_shots(shots)
        spans = (
            [staff_extent_of(s) for s in ready.shots]
            if self.settings.align_staff_ends
            else None
        )
        pages = paginate([s.effective_size for s in ready.shots], self.settings, spans)
        self._pages = pages
        self._usable_rows = ready.rows
        self._pdf_bytes = pdf.build(ready.shots, pages, self.settings)
        self.preview.set_pdf(self._pdf_bytes)
        self.export_button.setEnabled(bool(pages))
        self.export_action.setEnabled(bool(pages))
        self.musicxml_button.setEnabled(bool(pages) and self._musicxml_task is None)
        self._zoom_bar.setEnabled(bool(pages))
        self._refresh_list(shots, set(ready.missing), pages, ready.rows)
        text = self.tr("{captures}, {pages}").format(
            captures=self.tr("%n capture(s)", "", len(shots)),
            pages=self.tr("%n page(s)", "", len(pages)),
        )
        if ready.missing:
            text += self.tr(", %n file(s) missing", "", len(ready.missing))
        self.status.setText(f"{text} · {self._result}" if self._result else text)
        self._update_title()
        self._update_zoom_label()
        self._mark_selection()
        self._dirty = False

    def _refresh_list(
        self,
        shots: Sequence[Shot],
        missing: set[int],
        pages: Sequence[Page],
        rows: Sequence[int],
    ) -> None:
        page_of_row = {
            rows[placement.index]: number
            for number, page in enumerate(pages, start=1)
            for placement in page.placements
        }
        blocked = self.shot_list.blockSignals(True)
        current = self.shot_list.currentRow()
        chosen = self.shot_list.selected_rows()
        self.shot_list.clear()
        for index, shot in enumerate(shots):
            self.shot_list.add_row(
                row_data(
                    index,
                    shot,
                    self.settings,
                    missing=index in missing,
                    page=page_of_row.get(index),
                )
            )
        if 0 <= current < self.shot_list.count():
            self.shot_list.setCurrentRow(current)
        for row in chosen:
            if row < self.shot_list.count():
                self.shot_list.item(row).setSelected(True)
        self.shot_list.blockSignals(blocked)
        self._list_stack.setCurrentWidget(
            self.shot_list if shots else self.empty_state
        )
        self._update_actions()

    def _update_actions(self, *_args) -> None:
        rows = self.shot_list.selected_rows()
        # Editing and recapturing mean one capture; deleting can take several.
        self.recapture_button.setEnabled(len(rows) == 1)
        self.edit_button.setEnabled(len(rows) == 1)
        self.delete_button.setEnabled(bool(rows))
        self.undo_button.setEnabled(self.document.can_undo)
        self.redo_button.setEnabled(self.document.can_redo)

    def _on_row_changed(self, *_args) -> None:
        self._update_actions()
        self._mark_selection()

    def _mark_selection(self) -> None:
        """Show on the proof which capture the list has selected."""
        row = self.shot_list.currentRow()
        if row not in self._usable_rows or row not in self.shot_list.selected_rows():
            self.preview.mark_capture(None)
            return
        position = self._usable_rows.index(row)
        for number, page in enumerate(self._pages):
            for placement in page.placements:
                if placement.index == position:
                    self.preview.mark_capture(
                        number,
                        (placement.x, placement.y, placement.w, placement.h),
                    )
                    return

    def _update_zoom_label(self) -> None:
        self.zoom_label.setText(f"{round(self.preview.zoom * 100)} %")
        self.fit_button.setChecked(self.preview.fits_width)

    # --- updates ---------------------------------------------------------

    def _track(self, task: BackgroundTask) -> BackgroundTask:
        """Keep a task and its signals alive until it has reported - no longer.

        The window outlives every task, so signals parented to it would pile
        up over a session of imports; letting them go takes the finished task
        with them.
        """
        signals = task.signals
        self._running_tasks.add(task)

        def retire() -> None:
            self._running_tasks.discard(task)
            signals.deleteLater()

        signals.finished.connect(retire)
        return task

    def _update_check_task(self) -> UpdateCheck:
        signals = UpdateSignals(self)
        signals.found.connect(self._on_update_found)
        return self._track(UpdateCheck(self.updates, signals))

    def check_for_updates(self) -> None:
        available = self.updates.is_available()
        log.info("updates available to this copy: %s", available)
        if not available:
            return  # running from source, or not installed
        QThreadPool.globalInstance().start(self._update_check_task())

    def _on_update_found(self, update: PendingUpdate) -> None:
        log.info("downloading update %s", update.version)
        self.update_label.setText(
            self.tr("Downloading version {version} …").format(version=update.version)
        )
        self.update_label.show()
        self._start_download(update)

    def _start_download(self, update: PendingUpdate) -> None:
        signals = UpdateSignals(self)
        signals.done.connect(self._on_update_downloaded)
        task = self._track(UpdateDownload(self.updates, update, signals))
        QThreadPool.globalInstance().start(task)

    def _on_update_downloaded(self, update: PendingUpdate, ok: bool) -> None:
        if not ok:
            # Stay quiet; the next start tries again.
            self.update_label.hide()
            self.update_button.hide()
            return
        log.info("update %s ready", update.version)
        self._ready_update = update
        self.update_label.setText(
            self.tr("Version {version} is ready — it installs when you close ScoreCap").format(
                version=update.version
            )
        )
        self.update_label.show()
        self.update_button.setToolTip(
            self.tr("Restarts ScoreCap in version {version} right away").format(
                version=update.version
            )
        )
        self.update_button.show()

    def _restart_into_update(self) -> None:
        update = self._ready_update
        if update is None:
            return
        # Unsaved captures live in a temporary folder and would not survive.
        if not self._confirm_discard():
            return
        self._restarting = True
        if not self.updates.restart_into(update):
            self._restarting = False
            self.update_label.setText(
                self.tr("Restart not possible — the update installs when you close ScoreCap")
            )

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

    # --- remembered folders ----------------------------------------------

    def _last_folder(self, kind: str) -> str:
        """The folder a file dialog of this kind was last used in, if it still exists."""
        folder = self._store.value(f"last_folder/{kind}")
        if not folder or not Path(str(folder)).is_dir():
            return ""
        return str(folder)

    def _remember_folder(self, kind: str, path: Path) -> None:
        self._store.setValue(f"last_folder/{kind}", str(path.parent))

    def choose_scans(self) -> None:
        patterns = " ".join(f"*{suffix}" for suffix in sorted(SCAN_SUFFIXES))
        names, _ = QFileDialog.getOpenFileNames(
            self,
            self.tr("Import scans"),
            self._last_folder("scans"),
            self.tr("Scans ({patterns})").format(patterns=patterns),
        )
        if names:
            self._remember_folder("scans", Path(names[0]))
            self.import_files([Path(name) for name in names])

    @property
    def is_importing(self) -> bool:
        return self._scan_task is not None

    def import_files(self, paths: Sequence[Path]) -> None:
        paths = scan_files(paths)
        if not paths or self.is_importing:
            return
        signals = ScanSignals(self)
        signals.progress.connect(self.status.setText)
        signals.done.connect(self._on_scans_imported)
        self._scan_task = self._track(ScanImport(paths, self._temp_dir, signals))
        self.scan_button.setEnabled(False)
        self.status.setText(self.tr("Reading scans …"))
        QThreadPool.globalInstance().start(self._scan_task)

    def _on_scans_imported(self, result: ImportResult) -> None:
        self._scan_task = None
        self.scan_button.setEnabled(True)
        self._scan_sources.update(result.sources)
        if result.shots:
            self.document.extend(result.shots)
            self.rebuild()
        self.status.setText(self._import_summary(result))
        if result.errors:
            QMessageBox.warning(
                self, self.tr("Not everything was imported"), "\n".join(result.errors)
            )

    def _import_summary(self, result: ImportResult) -> str:
        text = self.tr("{systems} from {pages} imported").format(
            systems=self.tr("%n system(s)", "", len(result.shots)),
            pages=self.tr("%n page(s)", "", result.pages),
        )
        if result.whole:
            text += self.tr(" — no staff lines, kept whole: {pages}").format(
                pages=", ".join(result.whole)
            )
        if result.blank:
            text += self.tr(" — blank, skipped: {pages}").format(
                pages=", ".join(result.blank)
            )
        return text

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if scan_files([Path(url.toLocalFile()) for url in urls if url.isLocalFile()]):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        event.acceptProposedAction()
        self.import_files([Path(url.toLocalFile()) for url in urls if url.isLocalFile()])

    def arm_capture(self) -> None:
        """Step aside and wait for the hotkey.

        The button only gets out of the way; opening the overlay right here
        would freeze the screen before the user has scrolled to the passage
        they want.
        """
        self._pending_replace = None
        self._arm()

    def _single_row(self) -> int:
        """The one selected row, or -1 for none and for several."""
        rows = self.shot_list.selected_rows()
        return rows[0] if len(rows) == 1 else -1

    def recapture_selected(self) -> None:
        index = self._single_row()
        if index < 0:
            return
        self._pending_replace = index
        self._arm()

    def _enter_series(self) -> None:
        if not self._capturing:
            self._series_taken = 0
            self._take_retake_hotkey()
        self._capturing = True

    def _take_retake_hotkey(self) -> None:
        """Hold the key only now: outside a series it belongs to other programs.

        The Again button does the same job, so a key that is taken is no
        reason to interrupt the user at the start of a series.
        """
        if not self._hotkeys_installed:
            return
        try:
            if not self._retake_hotkey.register(self.settings.retake_hotkey):
                log.info("%s is in use", self.settings.retake_hotkey)
        except ValueError as error:
            log.info("retake hotkey not usable: %s", error)

    def _arm(self) -> None:
        self._enter_series()
        self.showMinimized()
        self._show_series_bar()

    def _show_series_bar(self, missed: bool = False) -> None:
        """Say where the series stands; the window itself is out of sight."""
        hotkey = self._hotkey_text()
        shots = self.document.shots
        if self._pending_replace is not None:
            title = self.tr("Recapture {number}").format(
                number=self._pending_replace + 1
            )
        elif self._series_taken:
            title = self.tr("Capture {number}").format(number=len(shots))
        else:
            title = self.tr("Series ready")
        if missed:
            hint = self.tr("That was too small. Press {hotkey} and drag again")
        elif self._series_taken:
            hint = self.tr("{hotkey} next · {retake} again")
        else:
            hint = self.tr("Scroll to the passage, press {hotkey} and drag")
        last = shots[-1] if self._series_taken else None
        retake = _shortcut_text(self.settings.retake_hotkey)
        self._series_bar.retake_button.setToolTip(
            self.tr("Take this capture back and drag it again ({shortcut})").format(
                shortcut=retake
            )
        )
        self._series_bar.show_state(
            title,
            hint.format(hotkey=hotkey, retake=retake),
            last.path if last else None,
            last.crop if last else None,
        )

    def _undo_in_series(self) -> None:
        """Take back the last capture; only this series', never older work."""
        if self._series_taken and self.document.undo():
            self._series_taken -= 1
            self._dirty = True
            self._show_series_bar()

    def retake_capture(self) -> None:
        """The last capture was wrong: back to dragging it, series running on."""
        if not self._capturing or not self._series_taken:
            return
        number = len(self.document.shots)
        if self.document.undo():
            self._series_taken -= 1
            self._dirty = True
            self.begin_capture(
                self.tr("Capture {number} taken back").format(number=number)
            )

    def _overlay_caption(self, note: str) -> str:
        """What the dimmed screen says; the window that could is out of sight."""
        end = self.tr("Esc ends the series")
        if not self._series_taken:
            return f"{note} · {end}" if note else end
        again = self.tr("{retake} or right-click: the last one again").format(
            retake=_shortcut_text(self.settings.retake_hotkey)
        )
        return " · ".join(part for part in (note, again, end) if part)

    def begin_capture(self, note: str = "") -> None:
        """What the hotkey does: dim the screen and let the user drag.

        Not while a dialog is open: it would take no drag - a modal dialog
        blocks every other window - and would hide the question being asked.
        """
        waiting = QApplication.activeModalWidget()
        if waiting is not None:
            # Silence would look like a broken hotkey; the question explains it.
            waiting.raise_()
            waiting.activateWindow()
            return
        self._enter_series()
        if not self.isMinimized():
            self.showMinimized()
        self._series_bar.hide()  # it would end up in the capture
        self._overlay.start(self._overlay_caption(note))

    def finish_capture(self) -> None:
        """Leave capture mode: show the window again and catch up on rendering."""
        self._capturing = False
        self._pending_replace = None
        self._series_bar.hide()
        self._retake_hotkey.unregister()
        self.showNormal()
        self.raise_()
        self.activateWindow()
        if self._dirty:
            self.rebuild()
        if self._series_taken:
            # Where the user left off: the newest capture, on its page.
            self.shot_list.setCurrentRow(self.shot_list.count() - 1)
            self._series_taken = 0

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
        self._series_taken += 1
        self._show_series_bar()

    def _on_missed(self) -> None:
        """A click or a slip must not cost the user their place in the score."""
        self._show_series_bar(missed=True)

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

    @property
    def pages(self) -> list[Page]:
        """The pages the preview currently shows."""
        return list(self._pages)

    def select_at(self, page_number: int, x: float, y: float) -> None:
        """A click on the proof picks that capture out of the list.

        Clicking bare paper - a margin, the gap between two systems - is no
        answer to "which capture?", so the selection stays where it was.
        """
        if not 0 <= page_number < len(self._pages):
            return
        position = placement_at(self._pages[page_number], x, y)
        if position is None or position >= len(self._usable_rows):
            return
        row = self._usable_rows[position]
        self.shot_list.setCurrentRow(row)
        self.shot_list.scrollToItem(self.shot_list.item(row))

    def _edit_item(self, item) -> None:
        self.shot_list.setCurrentItem(item)
        self.edit_selected()

    def edit_selected(self) -> None:
        index = self._single_row()
        if index < 0:
            return
        shot = self.document.shots[index]
        if not shot.path.exists():
            return  # nothing to show; the list already says the file is gone
        # The tool used last, also across restarts: someone cropping a whole
        # book should not have to switch away from the eraser every time.
        mode = self._store.value("edit/mode", EDIT_MODES[0])
        dialog = CropDialog(
            shot,
            self,
            self.palette_tokens,
            self._scan_sources.get(shot.path),
            mode=mode if mode in EDIT_MODES else EDIT_MODES[0],
        )
        accepted = dialog.exec()
        self._store.setValue("edit/mode", dialog.mode)
        if not accepted:
            return
        base = dialog.shot
        crop = dialog.crop
        if dialog.erasures != base.erasures:
            # Fresh white at an edge is white margin; let the crop close in.
            crop = crop_after_erasing(
                replace(base, crop=crop, erasures=dialog.erasures), self.settings
            )
        if base.path == shot.path:
            self.document.set_edits(index, crop, dialog.erasures)
        else:
            self.document.replace_shot(
                index, replace(base, crop=crop, erasures=dialog.erasures)
            )
        self.rebuild()

    def delete_selected(self) -> None:
        rows = self.shot_list.selected_rows()
        if not rows:
            return
        self.document.remove_many(rows)
        self.shot_list.clearSelection()
        self.rebuild()
        self.shot_list.setCurrentRow(min(rows[0], self.shot_list.count() - 1))

    def shift_selected(self, step: int) -> None:
        """Move the selected capture one row up or down, for the keyboard."""
        rows = self.shot_list.selected_rows()
        order = shifted_order(self.shot_list.count(), rows, step)
        if order is None:
            return
        self.document.arrange(order)
        self.shot_list.clearSelection()
        self.rebuild()
        for row in rows:
            self.shot_list.item(row + step).setSelected(True)
        self.shot_list.setCurrentRow(
            rows[0] + step, QItemSelectionModel.SelectionFlag.NoUpdate
        )

    def undo(self) -> None:
        if self.document.undo():
            self.rebuild()

    def redo(self) -> None:
        if self.document.redo():
            self.rebuild()

    def _on_rows_moved(self, *_args) -> None:
        # A drag of several rows arrives as one signal per row, and undo should
        # see one step: read the order once the drop is over.
        QTimer.singleShot(0, self._take_list_order)

    def _take_list_order(self) -> None:
        order = self.shot_list.order()
        if order != sorted(order):
            self.document.arrange(order)
            self.rebuild()

    def edit_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if not dialog.exec():
            return
        previous = self.settings
        self.settings = dialog.settings
        save_settings(self.settings, self._store)
        if self.settings.hotkey != previous.hotkey:
            self._register_hotkey()
            self._show_hotkey()
        self.rebuild()
        if self.settings.language != previous.language:
            QMessageBox.information(
                self,
                self.tr("Language"),
                self.tr("The language changes the next time ScoreCap starts."),
            )

    def shrink_pdf_file(self, source: Path, target: Path) -> OptimizeResult:
        """Write a shrunk copy of `source` to `target`, unless it cannot shrink."""
        result = optimize_pdf(source.read_bytes())  # ValueError if not a PDF
        if result.after >= result.before:
            self.status.setText(
                self.tr("{name} is already compact — nothing changed").format(name=source.name)
            )
            return result
        target.write_bytes(result.data)
        self.status.setText(
            self.tr("{name}: {before} → {after}, saved as {target}").format(
                name=source.name,
                before=_megabytes(result.before),
                after=_megabytes(result.after),
                target=target.name,
            )
        )
        return result

    def shrink_pdf(self) -> None:
        name, _ = QFileDialog.getOpenFileName(
            self, self.tr("Shrink PDF"), self._last_folder("pdf"), "PDF (*.pdf)"
        )
        if not name:
            return
        source = Path(name)
        self._remember_folder("pdf", source)
        target_name, _ = QFileDialog.getSaveFileName(
            self, self.tr("Save shrunk copy"), str(shrunk_name(source)), "PDF (*.pdf)"
        )
        if not target_name:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.shrink_pdf_file(source, Path(target_name))
        except (OSError, ValueError) as error:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, self.tr("Shrinking failed"), str(error))
        else:
            QApplication.restoreOverrideCursor()

    # --- projects -------------------------------------------------------

    @property
    def is_modified(self) -> bool:
        return self.document.revision != self._saved_revision

    def _update_title(self) -> None:
        name = self._project_path.stem if self._project_path else self.tr("Untitled")
        # [*] is where Qt shows the unsaved marker when windowModified is set.
        self.setWindowTitle(f"{name}[*] — ScoreCap")
        self.setWindowModified(self.is_modified)

    def _confirm_discard(self) -> bool:
        """True when it is fine to drop the current document."""
        if not self.is_modified or not self.document.shots:
            return True
        answer = ask_save_changes(self)
        if answer == "save":
            return self.save()
        return answer == "discard"

    def save_to(self, path: Path) -> None:
        ready = usable_shots(self.document.shots)
        save_project(path, ready.shots)
        self._project_path = path
        self._saved_revision = self.document.revision
        self._remember_folder("project", path)
        self._update_title()
        text = self.tr("Saved: {name}").format(name=path.name)
        if ready.missing:
            # They cannot be saved, and after reopening they would be gone
            # without ever having been mentioned.
            text += self.tr(
                " — %n capture(s) whose file is gone were left out",
                "",
                len(ready.missing),
            )
        self.status.setText(text)

    def save(self) -> bool:
        if self._project_path is None:
            return self.save_as()
        return self._save_reporting(self._project_path)

    def save_as(self) -> bool:
        folder = self._last_folder("project") or str(Path.home())
        suggestion = self._project_path or Path(folder) / f"{self.tr('Score')}{SUFFIX}"
        name, _ = QFileDialog.getSaveFileName(
            self, self.tr("Save project"), str(suggestion), project_filter()
        )
        if not name:
            return False
        path = Path(name)
        if path.suffix.lower() != SUFFIX:
            path = path.with_name(path.name + SUFFIX)
        return self._save_reporting(path)

    def _save_reporting(self, path: Path) -> bool:
        try:
            self.save_to(path)
        except OSError as error:
            QMessageBox.critical(
                self, self.tr("Saving failed"), self._write_failure(path, error)
            )
            return False
        return True

    def _write_failure(self, path: Path, error: OSError) -> str:
        """Why a file could not be written, in words that lead to a way out.

        A PDF that is open in a reader is by far the likeliest cause on
        Windows, and "[Errno 13]" says nothing about it.
        """
        log.info("could not write %s: %s", path, error)
        if isinstance(error, PermissionError):
            return self.tr(
                "{name} could not be written. Another program may have it open: "
                "close it there and try again."
            ).format(name=path.name)
        return self.tr("{name} could not be written: {reason}").format(
            name=path.name, reason=error.strerror or str(error)
        )

    def open_project(self) -> None:
        if not self._confirm_discard():
            return
        name, _ = QFileDialog.getOpenFileName(
            self, self.tr("Open project"), self._last_folder("project"), project_filter()
        )
        if name:
            self.load_from(Path(name))

    def load_from(self, path: Path) -> None:
        try:
            shots = load_project(path, self._temp_dir)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, self.tr("Opening failed"), str(error))
            return
        self.document.replace_all(shots)
        self._scan_sources.clear()
        self._project_path = path
        self._saved_revision = self.document.revision
        self._remember_folder("project", path)
        self._forget_result()
        self.rebuild()
        self.status.setText(self.tr("Opened: {name}").format(name=path.name))

    def musicxml_source(self) -> Path:
        """The score as Audiveris reads it best: grey, and without a footer.

        Grey beat black and white in every voice that was measured, and the
        footer sits where lyrics otherwise are. The print settings belong to
        the printer, not to the transcription.
        """
        settings = replace(self.settings, scan_mode="grey", footer_enabled=False)
        ready = usable_shots(self.document.shots)
        spans = (
            [staff_extent_of(s) for s in ready.shots]
            if settings.align_staff_ends
            else None
        )
        pages = paginate([s.effective_size for s in ready.shots], settings, spans)
        source = self._temp_dir / "for-audiveris.pdf"
        source.write_bytes(pdf.build(ready.shots, pages, settings))
        return source

    @property
    def is_transcribing(self) -> bool:
        return self._musicxml_task is not None

    def cancel_transcription(self) -> None:
        """Stop the running transcription; _on_musicxml_done reports it."""
        if self._musicxml_task is None:
            return
        self._musicxml_task.cancel()
        self.cancel_button.setEnabled(False)
        self.status.setText(self.tr("Stopping the transcription …"))

    def _show_running(self) -> None:
        self.musicxml_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()
        self._forget_result()
        self._show_progress(0, 0)

    def _forget_result(self) -> None:
        self._result = ""
        self._result_path = None
        self.result_button.hide()

    def _keep_result(self, text: str, path: Path) -> None:
        """Report a finished export until the next one, with a way to open it."""
        self._result = text
        self._result_path = path
        self.result_button.setToolTip(
            self.tr("Open {name} in its program").format(name=path.name)
        )
        self.result_button.show()
        self.status.setText(text)

    def open_result(self) -> None:
        path = self._result_path
        if path is None:
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            log.info("nothing opened %s", path)
            self.status.setText(
                self.tr("No program here opens {name}").format(name=path.name)
            )

    def export_musicxml_to(self, path: Path, run=omr.run_audiveris) -> None:
        """Start the transcription; the result arrives in _on_musicxml_done."""
        if self._musicxml_task is not None:
            return
        signals = MusicXmlSignals(self)
        signals.progress.connect(self._on_musicxml_progress)
        signals.done.connect(self._on_musicxml_done)
        self._musicxml_task = self._track(
            MusicXmlExport(
                self.musicxml_source(),
                path,
                self._temp_dir / "audiveris",
                signals,
                run=run,
            )
        )
        self._claude_usage = None
        self._show_running()
        self.status.setText(
            self.tr("Transcribing with Audiveris — this takes a while …")
        )
        QThreadPool.globalInstance().start(self._musicxml_task)

    def musicxml_systems(self) -> list[Image.Image]:
        """Each capture as Claude should see it: grey, erased and cropped."""
        settings = replace(self.settings, scan_mode="grey")
        return [
            pdf.shot_image(shot, settings)
            for shot in usable_shots(self.document.shots).shots
        ]

    def export_musicxml_with_claude_to(
        self, path: Path, backend: reader.Backend | None = None
    ) -> None:
        """Start Claude's reading; the result arrives in _on_musicxml_done.

        If the usage limit stopped a reading of these same captures, the
        user decides whether it carries on or starts over.
        """
        if self._musicxml_task is not None:
            return
        systems = self.musicxml_systems()
        folder = reader.work_folder(claude_work_root(), systems)
        resume = False
        if reader.paused(folder) is not None:
            choice = self.ask_resume()
            if choice is None:
                return
            resume = choice
        signals = MusicXmlSignals(self)
        signals.reading.connect(self._on_claude_progress)
        signals.done.connect(self._on_musicxml_done)
        self._musicxml_task = self._track(
            ClaudeExport(
                systems,
                path,
                folder,
                signals,
                backend=backend,
                resume=resume,
            )
        )
        self._claude_usage = reader.Usage()
        self._claude_reached = None
        self._show_running()
        if resume:
            self.status.setText(self.tr("Claude carries on where it stopped …"))
        else:
            self.status.setText(self.tr("Claude is reading the score …"))
        QThreadPool.globalInstance().start(self._musicxml_task)

    def ask_resume(self) -> bool | None:
        """Carry on with the stopped reading (True), start over, or not at all."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(self.tr("Carry on reading?"))
        box.setText(
            self.tr(
                "Claude's usage limit stopped an earlier reading of these "
                "captures. Carry on where it stopped, or start over?"
            )
        )
        box.setInformativeText(
            self.tr(
                "Carrying on is quicker, but Claude first takes in everything "
                "it read before - that counts towards the plan as well."
            )
        )
        carry_on = box.addButton(self.tr("Carry on"), QMessageBox.AcceptRole)
        start_over = box.addButton(self.tr("Start over"), QMessageBox.DestructiveRole)
        box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(carry_on)
        box.exec()
        if box.clickedButton() is carry_on:
            return True
        if box.clickedButton() is start_over:
            return False
        return None

    def zoom_text(self, reached: reader.Progress) -> str:
        """How often Claude had to magnify a piece to be sure of it.

        Often means the captures are too small to read well; a sharper
        capture or scan pays off in the next reading.
        """
        if not reached.zoomed:
            return self.tr("no system needed magnifying")
        systems = len({name.split("-zoom-")[0] for name in reached.zoomed})
        return self.tr("%n magnified piece(s)", "", len(reached.zoomed)) + self.tr(
            " in {systems} of {total} systems"
        ).format(systems=systems, total=reached.systems)

    def _show_progress(self, value: int, maximum: int) -> None:
        """Fill the bar to value of maximum; with no maximum it only runs."""
        self.progress_bar.setRange(0, maximum)
        self.progress_bar.setValue(value)
        self.progress_bar.show()

    def _on_claude_progress(self, reached: reader.Progress) -> None:
        """Claude opened another system, answered, or went back to mend.

        Opening the systems is the part that can be counted; writing the
        notation down and correcting it can only be waited for.
        """
        self._claude_usage = reached.usage
        self._claude_reached = reached
        if reached.attempt > 1:
            self._show_progress(0, 0)
            text = self.tr(
                "Claude is correcting bars that did not add up "
                "({attempt} of {total}) …"
            ).format(attempt=reached.attempt - 1, total=reached.attempts - 1)
        elif reached.looked < reached.systems:
            self._show_progress(reached.looked, reached.systems)
            text = self.tr("Claude is reading system {number} of {total} …").format(
                number=reached.looked + 1, total=reached.systems
            )
        else:
            self._show_progress(0, 0)
            text = self.tr("Claude is writing the notation down …")
        self.status.setText(text)

    def usage_text(self, usage: reader.Usage) -> str:
        """What a reading used, as the status line says it.

        On a subscription the tokens are not billed one by one, so the
        plan's limits come first; the API price is for those without one.
        """
        tokens = self.tr("{thousands} k tokens").format(
            thousands=QLocale().toString(round(usage.tokens_in / 1000))
        )
        if usage.five_hour is not None and usage.seven_day is not None:
            plan = self.tr(
                "plan used: {hours} % of five hours, {week} % of the week"
            ).format(
                hours=round(usage.five_hour * 100), week=round(usage.seven_day * 100)
            )
            return f"{tokens}, {plan}"
        price = self.tr("about {cost} US$ at API prices").format(
            cost=QLocale().toString(usage.cost_usd, "f", 2)
        )
        return f"{tokens}, {price}"

    def _reader_is_ready(self, reader_name: str) -> bool:
        """Is the program this reading needs there? If not, say so now.

        Asked before the file dialog: naming a file only to hear that the
        reading cannot start wastes the user's time.
        """
        try:
            if reader_name == "claude":
                reader.find_claude()
            else:
                omr.find_audiveris()
        except (omr.AudiverisMissing, reader.ClaudeMissing) as error:
            self._explain_setup(error)
            return False
        return True

    def export_musicxml(self, reader_name: str = "audiveris") -> None:
        if not self._reader_is_ready(reader_name):
            return
        stem = self._project_path.stem if self._project_path else self.tr("score")
        folder = self._last_folder("musicxml") or (
            str(self._project_path.parent) if self._project_path else ""
        )
        name, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Save as MusicXML"),
            str(Path(folder) / f"{stem}.musicxml"),
            self.tr("MusicXML (*.musicxml)"),
        )
        if name:
            self._remember_folder("musicxml", Path(name))
            if reader_name == "claude":
                self.export_musicxml_with_claude_to(Path(name))
            else:
                self.export_musicxml_to(Path(name))

    def _on_musicxml_progress(self, page: int, total: int) -> None:
        """Audiveris reached a new page. Before it says how many there are,
        the count is 0 and only the page number is worth showing."""
        if total:
            text = self.tr("Reading page {page} of {total} with Audiveris …")
            self._show_progress(page - 1, total)
        else:
            text = self.tr("Reading page {page} with Audiveris …")
        self.status.setText(text.format(page=page, total=total))

    def _explain_setup(self, outcome: Exception) -> bool:
        """Say what is missing for a reading; False if `outcome` is no such thing."""
        if isinstance(outcome, omr.AudiverisMissing):
            QMessageBox.information(
                self,
                self.tr("Audiveris is needed for this"),
                self.tr(
                    "ScoreCap has the pages; reading the notes off them is done by "
                    "Audiveris, a separate free program. Install it from {url} and "
                    "try again."
                ).format(url=omr.DOWNLOAD_URL),
            )
            return True
        if isinstance(outcome, reader.ClaudeMissing):
            QMessageBox.information(
                self,
                self.tr("Claude Code is needed for this"),
                self.tr(
                    "Reading the score with Claude goes through Claude Code. "
                    "Install it from {url}, sign in once by running claude, and "
                    "try again."
                ).format(url=reader.DOWNLOAD_URL),
            )
            return True
        if isinstance(outcome, reader.ClaudeLoggedOut):
            QMessageBox.information(
                self,
                self.tr("Claude Code is not signed in"),
                self.tr(
                    "Open a terminal, run claude and sign in with your Claude "
                    "account, then try again."
                ),
            )
            return True
        return False

    def _on_musicxml_done(self, outcome) -> None:
        self._musicxml_task = None
        # After a reading that took minutes the user may be anywhere else.
        if not self.isActiveWindow():
            QApplication.alert(self)
        self.musicxml_button.setEnabled(bool(self._pages))
        self.progress_bar.hide()
        self.cancel_button.hide()
        usage, self._claude_usage = self._claude_usage, None
        reached, self._claude_reached = self._claude_reached, None
        if self._explain_setup(outcome):
            return
        if isinstance(outcome, reader.LimitReached):
            if outcome.resets is not None:
                when = self.tr("until {time}").format(
                    time=QLocale().toString(outcome.resets.time(), QLocale.ShortFormat)
                )
            else:
                when = self.tr("for now")
            QMessageBox.information(
                self,
                self.tr("Claude's usage limit is reached"),
                self.tr(
                    "The plan's usage limit is used up {when}. What Claude has "
                    "read so far is kept: export with Claude again after that, "
                    "and it can carry on where it stopped."
                ).format(when=when),
            )
            self.status.setText(self.tr("Reading paused at the usage limit"))
            return
        if isinstance(outcome, omr.Cancelled):
            self.status.setText(self.tr("Transcription cancelled"))
            return
        if isinstance(outcome, Exception):
            QMessageBox.critical(self, self.tr("Transcription failed"), str(outcome))
            return
        text = self.tr("Transcribed: {name}").format(name=outcome.name)
        if usage is not None:
            text = f"{text} · {self.usage_text(usage)}"
        if reached is not None:
            text = f"{text} · {self.zoom_text(reached)}"
        self._keep_result(text, outcome)

    def export_to(self, path: Path) -> None:
        path.write_bytes(self._pdf_bytes)

    def export(self) -> None:
        stem = self._project_path.stem if self._project_path else self.tr("score")
        folder = self._last_folder("pdf") or (
            str(self._project_path.parent) if self._project_path else ""
        )
        name, _ = QFileDialog.getSaveFileName(
            self, self.tr("Save as PDF"), str(Path(folder) / f"{stem}.pdf"), "PDF (*.pdf)"
        )
        if not name:
            return
        try:
            self.export_to(Path(name))
        except OSError as error:
            QMessageBox.critical(
                self, self.tr("Export failed"), self._write_failure(Path(name), error)
            )
        else:
            self._remember_folder("pdf", Path(name))
            self._keep_result(
                self.tr("Exported: {name}").format(name=Path(name).name), Path(name)
            )

    def closeEvent(self, event) -> None:  # noqa: N802
        running = self._musicxml_task
        if running is not None and not ask_stop_transcription(self):
            event.ignore()
            return
        if not self._restarting and not self._confirm_discard():
            event.ignore()
            return
        if self._ready_update is not None and not self._restarting:
            self.updates.install_on_exit(self._ready_update)
        # The overlay is deliberately parentless (a child window would be
        # hidden along with the minimised main window), so close it by hand.
        self._overlay.hide()
        self._overlay.deleteLater()
        self._series_bar.hide()
        self._series_bar.deleteLater()
        self._hotkey.unregister()
        self._retake_hotkey.unregister()
        if self._scan_task is not None:
            # It writes into the session folder that is about to go.
            self._scan_task.cancel()
            self._scan_task.stopped.wait(CLOSE_WAIT_S)
        if running is not None:
            # Audiveris works in that folder too.
            running.cancel()
            running.stopped.wait(CLOSE_WAIT_S)
        # Whatever is still in there goes with it: a cancelled import may
        # not have stopped writing, and a half-written file must not keep
        # the window from closing.
        shutil.rmtree(self._temp_dir, ignore_errors=True)
        super().closeEvent(event)
