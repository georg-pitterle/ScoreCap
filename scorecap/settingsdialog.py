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
    QVBoxLayout,
    QWidget,
)

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
        self.setWindowTitle("Einstellungen")
        self._base = settings
        self._margin_side = _spin(settings.margin_side_mm, 0.0, 50.0, 1.0, 1)
        self._margin_top = _spin(settings.margin_top_mm, 0.0, 50.0, 1.0, 1)
        self._margin_bottom = _spin(settings.margin_bottom_mm, 0.0, 50.0, 1.0, 1)
        self._gap_min = _spin(settings.gap_min_mm, 0.0, 30.0, 0.5, 1)
        self._shrink_min = _spin(settings.shrink_min, 0.70, 1.00, 0.01, 2)
        self._min_dpi = _spin(settings.min_dpi, 0.0, 600.0, 10.0, 0)
        self._footer = QCheckBox("Seitenzahl als Fußzeile")
        self._footer.setChecked(settings.footer_enabled)
        self._auto_trim = QCheckBox("Weiße Ränder automatisch abschneiden")
        self._auto_trim.setChecked(settings.auto_trim)
        self._align_staff_ends = QCheckBox("Notenlinien bündig ausrichten")
        self._align_staff_ends.setToolTip(
            "Notenlinien beginnen am linken und enden am rechten Rand; Klammern "
            "davor und Zeichen dahinter, etwa Teilungspfeile, ragen in den Seitenrand"
        )
        self._align_staff_ends.setChecked(settings.align_staff_ends)
        self._hotkey = QLineEdit(settings.hotkey)
        self._scan_mode = QComboBox()
        self._scan_mode.addItem("Schwarz/Weiß", "bw")
        self._scan_mode.addItem("Graustufen", "grey")
        self._scan_mode.setToolTip(
            "Schwarz/Weiß druckt am saubersten und ergibt die kleinsten PDFs; "
            "Graustufen bleiben näher am Original"
        )
        self._scan_mode.setCurrentIndex(max(0, self._scan_mode.findData(settings.scan_mode)))

        form = QFormLayout()
        form.addRow("Rand seitlich (mm)", self._margin_side)
        form.addRow("Rand oben (mm)", self._margin_top)
        form.addRow("Rand unten (mm)", self._margin_bottom)
        form.addRow("Mindestabstand (mm)", self._gap_min)
        form.addRow("Kleinster Schrumpffaktor", self._shrink_min)
        form.addRow("Warnschwelle dpi", self._min_dpi)
        form.addRow("Hotkey", self._hotkey)
        form.addRow("Scans bereinigen", self._scan_mode)
        form.addRow(self._footer)
        form.addRow(self._auto_trim)
        form.addRow(self._align_staff_ends)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Speichern")
        buttons.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

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
        )
