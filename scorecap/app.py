"""Main window: captures on the left, the printed proof on the right."""

from __future__ import annotations

import logging
import sys
import tempfile
import threading
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QLocale,
    QObject,
    QRunnable,
    QSettings,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import QAction, QCursor, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
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
from .layout import Page, paginate, placement_at
from .optimize import OptimizeResult, optimize_pdf
from .model import Document, Shot, normalize_move
from .preview import PreviewWidget
from .project import SUFFIX, load_project, save_project
from .scan import SUFFIXES as SCAN_SUFFIXES
from .scan import ImportResult, import_scans
from .settingsdialog import SettingsDialog, load_settings, save_settings
from .shotlist import ShotList, row_data
from .staff import staff_extent_of
from .theme import Palette, palette_for, stylesheet, system_prefers_dark
from .trim import auto_crop
from .updater import PendingUpdate, UpdateService

REBUILD_DELAY_MS = 150
# Not Ctrl+Shift+S for "save as": that is the global capture hotkey.
SAVE_AS_KEY = "F12"
SCAN_CLOSE_WAIT_S = 10.0
TOAST_MS = 900
TOAST_MARGIN_PX = 8
TOAST_OFFSET_PX = 12
ZOOM_STEP = 1.25
UPDATE_CHECK_DELAY_MS = 2000

log = logging.getLogger(__name__)


class _UpdateSignals(QObject):
    """Created on the UI thread and parented to the window.

    A QRunnable is not a QObject and nothing keeps its Python wrapper alive
    once the pool has it, so signals owned by the task itself can be
    collected mid-run - the result then vanishes with "Signal source has been
    deleted". Owned by the window, they live exactly as long as the receiver.
    """

    found = Signal(object)
    done = Signal(object, bool)
    finished = Signal()


class _ScanSignals(QObject):
    """Owned by the window for the same reason as _UpdateSignals."""

    progress = Signal(str)
    done = Signal(object)
    finished = Signal()


def settings_store() -> QSettings:
    """Where settings and remembered folders live: the user's registry."""
    return QSettings("ScoreCap", "ScoreCap")


def _attach_debugger_to_this_thread() -> None:
    """Let breakpoints fire in a Qt pool thread.

    debugpy only traces threads Python's threading module started; Qt's
    QThreadPool threads are invisible to it, so a breakpoint in a task's run()
    would never hit. Outside a debug session debugpy is not loaded and this
    does nothing.
    """
    debugpy = sys.modules.get("debugpy")
    if debugpy is None:
        return
    try:
        # Without a connected client, debug_this_thread() tries to connect
        # itself: a stall of several seconds and a traceback per task.
        if debugpy.is_client_connected():
            debugpy.debug_this_thread()
    except Exception:  # noqa: BLE001 - a debugging aid must never break the app
        pass


def _emit(signal, *args) -> None:
    """Deliver a result unless the window is already gone."""
    try:
        signal.emit(*args)
    except RuntimeError:
        log.info("window closed before a background result arrived")


class _UpdateCheck(QRunnable):
    """Asks GitHub for a newer release without holding up the window."""

    def __init__(self, service: UpdateService, signals: _UpdateSignals | None = None) -> None:
        super().__init__()
        self.signals = signals or _UpdateSignals()
        self._service = service

    def run(self) -> None:
        _attach_debugger_to_this_thread()
        # Runs on a pool thread: an exception here would otherwise vanish.
        log.info("update check started")
        try:
            update = self._service.check()
        except BaseException:  # noqa: BLE001 - logged, never raised into Qt
            log.exception("update check crashed")
            update = None
        else:
            log.info(
                "update check finished: %s", update.version if update else "up to date"
            )
        if update is not None:
            _emit(self.signals.found, update)
        _emit(self.signals.finished)


class _ScanImport(QRunnable):
    """Cleans scanned pages and cuts them into systems, off the UI thread."""

    def __init__(self, paths: list[Path], target_dir: Path, signals: _ScanSignals) -> None:
        super().__init__()
        self.signals = signals
        self._paths = paths
        self._target_dir = target_dir
        self._cancelled = threading.Event()
        self.stopped = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def run(self) -> None:
        _attach_debugger_to_this_thread()
        log.info("scan import of %d file(s) started", len(self._paths))
        try:
            result = import_scans(
                self._paths,
                self._target_dir,
                progress=lambda text: _emit(self.signals.progress, text),
                cancelled=self._cancelled.is_set,
            )
        except BaseException:  # noqa: BLE001 - logged, never raised into Qt
            log.exception("scan import crashed")
            aborted = QCoreApplication.translate("MainWindow", "The import was aborted.")
            result = ImportResult([], 0, [], [], [aborted])
        finally:
            self.stopped.set()
        log.info("scan import finished: %d shot(s)", len(result.shots))
        _emit(self.signals.done, result)
        _emit(self.signals.finished)


def scan_files(paths: Sequence[Path]) -> list[Path]:
    """The paths a scan import can read, by their suffix."""
    return [path for path in paths if path.suffix.lower() in SCAN_SUFFIXES]


class _UpdateDownload(QRunnable):
    """Fetches an update in the background; reports success either way."""

    def __init__(
        self,
        service: UpdateService,
        update: PendingUpdate,
        signals: _UpdateSignals | None = None,
    ) -> None:
        super().__init__()
        self.signals = signals or _UpdateSignals()
        self._service = service
        self._update = update

    def run(self) -> None:
        _attach_debugger_to_this_thread()
        try:
            ok = bool(self._service.download(self._update))
        except BaseException:  # noqa: BLE001 - logged, never raised into Qt
            log.exception("update download crashed")
            ok = False
        _emit(self.signals.done, self._update, ok)
        _emit(self.signals.finished)


def _shortcut_text(key: QKeySequence.StandardKey) -> str:
    """A standard shortcut as the user's language writes it, e.g. Strg+O."""
    return QKeySequence(key).toString(QKeySequence.SequenceFormat.NativeText)


def shrunk_name(source: Path) -> Path:
    """Where a shrunk copy goes by default: beside the original, never over it."""
    suffix = QCoreApplication.translate("MainWindow", "-small")
    return source.with_name(f"{source.stem}{suffix}{source.suffix}")


def _megabytes(size: int) -> str:
    return QLocale().toString(size / 1024 / 1024, "f", 1) + " MB"


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
        self._pending_replace: int | None = None
        self._scan_task: _ScanImport | None = None
        self._capturing = False
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
        self.capture_button = self._button(self.tr("Prepare capture"), icons.CAPTURE, "Primary")
        self.capture_button.clicked.connect(self.arm_capture)
        self.capture_button.setToolTip(
            self.tr("The window steps aside; capturing starts only with the hotkey")
        )
        self.scan_button = self._button(self.tr("Import scans …"), icons.SCAN)
        self.scan_button.setToolTip(
            self.tr(
                "Clean up scanned pages (PDF or images) and split them into systems; "
                "files can also be dropped onto the window"
            )
        )
        self.scan_button.clicked.connect(self.choose_scans)
        self.recapture_button = self._button(self.tr("Recapture"), icons.RECAPTURE)
        self.recapture_button.clicked.connect(self.recapture_selected)
        self.edit_button = self._button(self.tr("Edit"), icons.EDIT)
        self.edit_button.setToolTip(
            self.tr("Crop the capture or erase what disturbs")
        )
        self.edit_button.clicked.connect(self.edit_selected)
        self.delete_button = self._button(self.tr("Delete"), icons.DELETE)
        self.delete_button.clicked.connect(self.delete_selected)
        self.settings_button = self._button(self.tr("Settings"), icons.SETTINGS)
        self.settings_button.clicked.connect(self.edit_settings)
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
        self.shrink_button = self._button(self.tr("Shrink PDF …"), icons.SHRINK)
        self.shrink_button.setToolTip(
            self.tr("Shrink an existing PDF; the original stays unchanged")
        )
        self.shrink_button.clicked.connect(self.shrink_pdf)

        toolbar = QWidget()
        toolbar.setObjectName("Toolbar")
        bar = QHBoxLayout(toolbar)
        bar.setContentsMargins(12, 8, 12, 8)
        bar.setSpacing(8)
        bar.addWidget(self.capture_button)
        bar.addWidget(self.scan_button)
        bar.addSpacing(8)
        for button in (self.recapture_button, self.edit_button, self.delete_button):
            bar.addWidget(button)
        bar.addStretch(1)
        bar.addWidget(self.open_button)
        bar.addWidget(self.save_button)
        bar.addSpacing(8)
        bar.addWidget(self.shrink_button)
        bar.addWidget(self.settings_button)

        self.shot_list = ShotList(self.palette_tokens)
        self.shot_list.model().rowsMoved.connect(self._on_rows_moved)
        self.shot_list.currentRowChanged.connect(self._update_actions)
        self.shot_list.itemDoubleClicked.connect(self._edit_item)

        self.empty_state = QLabel(
            self.tr("Nothing captured yet.\n\nPress {hotkey}, then drag out the area.").format(
                hotkey=self.settings.hotkey
            )
        )
        self.empty_state.setObjectName("EmptyState")
        self.empty_state.setAlignment(Qt.AlignCenter)
        self.empty_state.setWordWrap(True)

        self._list_stack = QStackedWidget()
        self._list_stack.addWidget(self.empty_state)
        self._list_stack.addWidget(self.shot_list)

        heading = QLabel(self.tr("Captures"))
        heading.setObjectName("Heading")

        side = QWidget()
        side.setObjectName("SidePanel")
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(12, 12, 12, 12)
        side_layout.setSpacing(8)
        side_layout.addWidget(heading)
        side_layout.addWidget(self._list_stack, 1)

        self.preview = PreviewWidget(self.palette_tokens)
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

        self.status = QLabel(self.tr("No capture yet"))
        self.status.setObjectName("StatusText")
        self.update_label = QLabel()
        self.update_label.setObjectName("StatusText")
        self.update_label.hide()
        self.update_button = self._button(self.tr("Restart now"), icons.RECAPTURE, "Primary")
        self.update_button.clicked.connect(self._restart_into_update)
        self.update_button.hide()
        self.export_button = self._button(self.tr("Export as PDF"), icons.EXPORT, "Primary")
        self.export_button.clicked.connect(self.export)
        self.export_button.setEnabled(False)

        status_bar = QWidget()
        status_bar.setObjectName("StatusBar")
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(12, 8, 12, 8)
        status_layout.addWidget(self.status, 1)
        status_layout.addWidget(self.update_label)
        status_layout.addWidget(self.update_button)
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

        undo_action = QAction(self.tr("Undo"), self)
        undo_action.setShortcut(QKeySequence.Undo)
        undo_action.triggered.connect(self.undo)
        self.addAction(undo_action)
        # Not Ctrl+Shift+S for "save as": that is the global capture hotkey.
        for label, keys, slot in (
            (self.tr("Open"), QKeySequence.Open, self.open_project),
            (self.tr("Save"), QKeySequence.Save, self.save),
            (self.tr("Save as"), QKeySequence(SAVE_AS_KEY), self.save_as),
        ):
            action = QAction(label, self)
            action.setShortcut(keys)
            action.triggered.connect(slot)
            self.addAction(action)
        self._update_title()
        self._update_actions()

    def _build_zoom_bar(self) -> QWidget:
        self.zoom_out_button = self._button("", icons.ZOOM_OUT)
        self.zoom_out_button.setToolTip(self.tr("Zoom out"))
        self.zoom_out_button.clicked.connect(lambda: self._step_zoom(1 / ZOOM_STEP))
        self.zoom_in_button = self._button("", icons.ZOOM_IN)
        self.zoom_in_button.setToolTip(self.tr("Zoom in"))
        self.zoom_in_button.clicked.connect(lambda: self._step_zoom(ZOOM_STEP))
        self.fit_button = self._button(self.tr("Fit"), icons.ZOOM_FIT)
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

        self.updates = UpdateService()
        self._ready_update: PendingUpdate | None = None
        self._restarting = False
        # Keeps each background task's wrapper alive until it has reported.
        self._running_tasks: set[QRunnable] = set()
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
        if not self._hotkey.register(self.settings.hotkey):
            QMessageBox.warning(
                self,
                self.tr("Hotkey taken"),
                self.tr(
                    "The hotkey {hotkey} is already in use. It can be changed in the settings."
                ).format(hotkey=self.settings.hotkey),
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
        spans = (
            [staff_extent_of(s) for s in usable] if self.settings.align_staff_ends else None
        )
        pages = paginate([s.effective_size for s in usable], self.settings, spans)
        self._pages = pages
        gone = set(missing)
        self._usable_rows = [i for i in range(len(shots)) if i not in gone]
        self._pdf_bytes = pdf.build(usable, pages, self.settings)
        self.preview.set_pdf(self._pdf_bytes)
        self.export_button.setEnabled(bool(pages))
        self._refresh_list(shots, set(missing))
        text = self.tr("{captures}, {pages}").format(
            captures=self.tr("%n capture(s)", "", len(shots)),
            pages=self.tr("%n page(s)", "", len(pages)),
        )
        if missing:
            text += self.tr(", %n file(s) missing", "", len(missing))
        self.status.setText(text)
        self._update_title()
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
        for button in (self.recapture_button, self.edit_button, self.delete_button):
            button.setEnabled(has_selection)

    def _update_zoom_label(self) -> None:
        self.zoom_label.setText(f"{round(self.preview.zoom * 100)} %")
        self.fit_button.setChecked(self.preview.fits_width)

    # --- updates ---------------------------------------------------------

    def _track(self, task: QRunnable) -> QRunnable:
        self._running_tasks.add(task)
        task.signals.finished.connect(lambda: self._running_tasks.discard(task))
        return task

    def _update_check_task(self) -> _UpdateCheck:
        signals = _UpdateSignals(self)
        signals.found.connect(self._on_update_found)
        return self._track(_UpdateCheck(self.updates, signals))

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
        signals = _UpdateSignals(self)
        signals.done.connect(self._on_update_downloaded)
        task = self._track(_UpdateDownload(self.updates, update, signals))
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
        signals = _ScanSignals(self)
        signals.progress.connect(self.status.setText)
        signals.done.connect(self._on_scans_imported)
        self._scan_task = self._track(
            _ScanImport(list(paths), self._temp_dir, signals)
        )
        self.scan_button.setEnabled(False)
        self.status.setText(self.tr("Reading scans …"))
        QThreadPool.globalInstance().start(self._scan_task)

    def _on_scans_imported(self, result: ImportResult) -> None:
        self._scan_task = None
        self.scan_button.setEnabled(True)
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

    def recapture_selected(self) -> None:
        index = self.shot_list.currentRow()
        if index < 0:
            return
        self._pending_replace = index
        self._arm()

    def _arm(self) -> None:
        self._capturing = True
        self.showMinimized()
        self._hint(self.tr("Ready — press {hotkey}").format(hotkey=self.settings.hotkey))

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
        self._show_toast(
            rect, self.tr("Capture {number}").format(number=len(self.document.shots))
        )

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
        index = self.shot_list.currentRow()
        if index < 0:
            return
        shot = self.document.shots[index]
        if not shot.path.exists():
            return  # nothing to show; the list already says the file is gone
        dialog = CropDialog(shot, self, self.palette_tokens)
        if dialog.exec():
            self.document.set_edits(index, dialog.crop, dialog.erasures)
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
        previous = self.settings
        self.settings = dialog.settings
        save_settings(self.settings, self._store)
        if self.settings.hotkey != previous.hotkey:
            self._hotkey.register(self.settings.hotkey)
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

    def _unsaved_changes_box(self) -> tuple[QMessageBox, QPushButton, QPushButton]:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(self.tr("Unsaved captures"))
        box.setText(self.tr("The captures have not been saved."))
        box.setInformativeText(self.tr("Unsaved captures are lost when ScoreCap closes."))
        save = box.addButton(self.tr("Save"), QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton(self.tr("Don't save"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(self.tr("Cancel"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        # The message box sizes its buttons before the window's stylesheet
        # has styled them, and the stylesheet's larger font then cut
        # the German "Nicht speichern" off. Styling them first fixes the widths.
        for button in box.buttons():
            button.ensurePolished()
            button.setMinimumWidth(button.sizeHint().width())
        return box, save, discard

    def _ask_save_changes(self) -> str:
        """'save', 'discard' or 'cancel' for unsaved work."""
        box, save, discard = self._unsaved_changes_box()
        box.exec()
        clicked = box.clickedButton()
        if clicked is save:
            return "save"
        if clicked is discard:
            return "discard"
        return "cancel"

    def _confirm_discard(self) -> bool:
        """True when it is fine to drop the current document."""
        if not self.is_modified or not self.document.shots:
            return True
        answer = self._ask_save_changes()
        if answer == "save":
            return self.save()
        return answer == "discard"

    def save_to(self, path: Path) -> None:
        usable, _missing = usable_shots(self.document.shots)
        save_project(path, usable)
        self._project_path = path
        self._saved_revision = self.document.revision
        self._remember_folder("project", path)
        self._update_title()
        self.status.setText(self.tr("Saved: {name}").format(name=path.name))

    def save(self) -> bool:
        if self._project_path is None:
            return self.save_as()
        return self._save_reporting(self._project_path)

    def save_as(self) -> bool:
        folder = self._last_folder("project") or str(Path.home())
        suggestion = self._project_path or Path(folder) / f"{self.tr('Score')}{SUFFIX}"
        name, _ = QFileDialog.getSaveFileName(
            self, self.tr("Save project"), str(suggestion), self._project_filter()
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
            QMessageBox.critical(self, self.tr("Saving failed"), str(error))
            return False
        return True

    def open_project(self) -> None:
        if not self._confirm_discard():
            return
        name, _ = QFileDialog.getOpenFileName(
            self, self.tr("Open project"), self._last_folder("project"), self._project_filter()
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
        self._project_path = path
        self._saved_revision = self.document.revision
        self._remember_folder("project", path)
        self.rebuild()
        self.status.setText(self.tr("Opened: {name}").format(name=path.name))

    def _project_filter(self) -> str:
        return self.tr("ScoreCap project (*{suffix})").format(suffix=SUFFIX)

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
            QMessageBox.critical(self, self.tr("Export failed"), str(error))
        else:
            self._remember_folder("pdf", Path(name))
            self.status.setText(self.tr("Exported: {name}").format(name=name))

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self._restarting and not self._confirm_discard():
            event.ignore()
            return
        if self._ready_update is not None and not self._restarting:
            self.updates.install_on_exit(self._ready_update)
        # The overlay is deliberately parentless (a child window would be
        # hidden along with the minimised main window), so close it by hand.
        self._overlay.hide()
        self._overlay.deleteLater()
        self._toast.hide()
        self._hotkey.unregister()
        if self._scan_task is not None:
            # It writes into the session folder that is about to go.
            self._scan_task.cancel()
            self._scan_task.stopped.wait(SCAN_CLOSE_WAIT_S)
        for file in self._temp_dir.glob("*.png"):
            file.unlink(missing_ok=True)
        self._temp_dir.rmdir()
        super().closeEvent(event)
