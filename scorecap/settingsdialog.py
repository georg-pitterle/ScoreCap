"""Settings dialog plus QSettings persistence."""

from __future__ import annotations

from dataclasses import fields

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from .hotkey import parse_hotkey
from .i18n import LANGUAGES
from .settings import Settings


def save_settings(settings: Settings, store: QSettings) -> None:
    for field in fields(Settings):
        store.setValue(field.name, getattr(settings, field.name))
    store.sync()


def _coerce(raw: object, default: object) -> object:
    """QSettings hands back strings; fall back to the default on junk."""
    if raw is None:
        return default
    try:
        if isinstance(default, bool):
            if isinstance(raw, str):
                lowered = raw.strip().lower()
                if lowered not in {"true", "false", "1", "0"}:
                    return default
                return lowered in {"true", "1"}
            return bool(raw)
        if isinstance(default, float):
            return float(raw)
        return type(default)(raw)
    except (TypeError, ValueError):
        return default


def load_settings(store: QSettings) -> Settings:
    defaults = Settings()
    values = {
        field.name: _coerce(store.value(field.name), getattr(defaults, field.name))
        for field in fields(Settings)
    }
    return Settings(**values)


def _spin(value: float, low: float, high: float, step: float, decimals: int) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(low, high)
    box.setSingleStep(step)
    box.setDecimals(decimals)
    box.setValue(value)
    return box


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Settings"))
        self._base = settings
        self._margin_side = _spin(settings.margin_side_mm, 0.0, 50.0, 1.0, 1)
        self._margin_top = _spin(settings.margin_top_mm, 0.0, 50.0, 1.0, 1)
        self._margin_bottom = _spin(settings.margin_bottom_mm, 0.0, 50.0, 1.0, 1)
        self._gap_min = _spin(settings.gap_min_mm, 0.0, 30.0, 0.5, 1)
        self._shrink_min = _spin(settings.shrink_min, 0.70, 1.00, 0.01, 2)
        self._min_dpi = _spin(settings.min_dpi, 0.0, 600.0, 10.0, 0)
        self._footer = QCheckBox(self.tr("Page number as footer"))
        self._footer.setChecked(settings.footer_enabled)
        self._auto_trim = QCheckBox(self.tr("Trim white margins automatically"))
        self._auto_trim.setChecked(settings.auto_trim)
        self._align_staff_ends = QCheckBox(self.tr("Align staff lines flush"))
        self._align_staff_ends.setToolTip(
            self.tr(
                "Staff lines start at the left and end at the right margin; braces before "
                "them and marks after them, such as divisi arrows, hang into the page margin"
            )
        )
        self._align_staff_ends.setChecked(settings.align_staff_ends)
        self._hotkey = QLineEdit(settings.hotkey)
        self._hotkey.setToolTip(
            self.tr("One or more modifiers and a key, for example Ctrl+Shift+S")
        )
        self._scan_mode = QComboBox()
        self._scan_mode.addItem(self.tr("Black and white"), "bw")
        self._scan_mode.addItem(self.tr("Greyscale"), "grey")
        self._scan_mode.setToolTip(
            self.tr(
                "How imported scans appear in the preview and the PDF. Black and white "
                "makes the smallest PDFs, greyscale smoother edges. Applies at once, also "
                "to scans already imported; screen captures stay grey"
            )
        )
        self._scan_mode.setCurrentIndex(max(0, self._scan_mode.findData(settings.scan_mode)))
        self._language = QComboBox()
        self._language.addItem(self.tr("System default"), "")
        for code, name in LANGUAGES.items():
            self._language.addItem(name, code)  # each language in its own words
        self._language.setToolTip(self.tr("Takes effect the next time ScoreCap starts"))
        self._language.setCurrentIndex(max(0, self._language.findData(settings.language)))

        form = QFormLayout()
        form.addRow(self.tr("Side margin (mm)"), self._margin_side)
        form.addRow(self.tr("Top margin (mm)"), self._margin_top)
        form.addRow(self.tr("Bottom margin (mm)"), self._margin_bottom)
        form.addRow(self.tr("Minimum gap (mm)"), self._gap_min)
        form.addRow(self.tr("Smallest shrink factor"), self._shrink_min)
        form.addRow(self.tr("Warning threshold dpi"), self._min_dpi)
        form.addRow(self.tr("Hotkey"), self._hotkey)
        form.addRow(self.tr("Print scans in"), self._scan_mode)
        form.addRow(self.tr("Language"), self._language)
        form.addRow(self._footer)
        form.addRow(self._auto_trim)
        form.addRow(self._align_staff_ends)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(self.tr("Save"))
        buttons.button(QDialogButtonBox.Cancel).setText(self.tr("Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def accept(self) -> None:  # noqa: D102 - QDialog's own slot
        """Refuse a hotkey that is no hotkey, rather than saving it.

        Saved, it would be read again at every start, where nothing can be
        typed to put it right.
        """
        try:
            parse_hotkey(self.settings.hotkey)
        except ValueError:
            QMessageBox.warning(
                self,
                self.tr("Hotkey"),
                self.tr(
                    "{hotkey} is not a usable hotkey. It needs one or more "
                    "modifiers and a key, for example Ctrl+Shift+S."
                ).format(hotkey=self._hotkey.text().strip()),
            )
            self._hotkey.setFocus()
            self._hotkey.selectAll()
            return
        super().accept()

    @property
    def settings(self) -> Settings:
        return Settings(
            margin_side_mm=self._margin_side.value(),
            margin_top_mm=self._margin_top.value(),
            margin_bottom_mm=self._margin_bottom.value(),
            gap_min_mm=self._gap_min.value(),
            gap_max_factor=self._base.gap_max_factor,
            shrink_min=self._shrink_min.value(),
            footer_enabled=self._footer.isChecked(),
            min_dpi=self._min_dpi.value(),
            hotkey=self._hotkey.text().strip() or self._base.hotkey,
            auto_trim=self._auto_trim.isChecked(),
            align_staff_ends=self._align_staff_ends.isChecked(),
            trim_threshold=self._base.trim_threshold,
            trim_padding_px=self._base.trim_padding_px,
            scan_mode=self._scan_mode.currentData(),
            language=self._language.currentData(),
        )
