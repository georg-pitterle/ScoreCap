import pytest
from PySide6.QtCore import QSettings

from scorecap.settings import Settings
from scorecap.settingsdialog import load_settings, save_settings


@pytest.fixture()
def store(tmp_path):
    return QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)


def test_roundtrip_keeps_every_field(store):
    original = Settings(
        margin_side_mm=15.5,
        margin_top_mm=9.0,
        margin_bottom_mm=18.0,
        gap_min_mm=6.0,
        gap_max_factor=2.0,
        shrink_min=0.7,
        footer_enabled=False,
        min_dpi=150.0,
        hotkey="Alt+F9",
        auto_trim=False,
        align_staff_ends=False,
        trim_threshold=200,
        trim_padding_px=7,
        scan_mode="grey",
    )
    save_settings(original, store)
    assert load_settings(store) == original


def test_empty_store_yields_defaults(store):
    assert load_settings(store) == Settings()


def test_corrupt_values_fall_back_to_defaults(store):
    store.setValue("margin_side_mm", "nonsense")
    store.setValue("footer_enabled", "nonsense")
    loaded = load_settings(store)
    assert loaded.margin_side_mm == Settings().margin_side_mm
    assert loaded.footer_enabled == Settings().footer_enabled


def test_dialog_returns_the_edited_settings(qapp):
    from scorecap.settingsdialog import SettingsDialog

    dialog = SettingsDialog(Settings())
    dialog._shrink_min.setValue(0.70)
    dialog._footer.setChecked(False)
    dialog._auto_trim.setChecked(False)
    dialog._align_staff_ends.setChecked(False)
    dialog._scan_mode.setCurrentIndex(dialog._scan_mode.findData("grey"))
    assert dialog.settings.shrink_min == pytest.approx(0.70)
    assert dialog.settings.footer_enabled is False
    assert dialog.settings.auto_trim is False
    assert dialog.settings.align_staff_ends is False
    assert dialog.settings.scan_mode == "grey"
