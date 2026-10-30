"""Colour and type tokens, plus the Qt stylesheet built from them.

The palette comes from the world the tool serves: printed sheet music. The
single accent is the deep ultramarine of urtext editions rather than the
default system blue, the chrome is warm neutral rather than the usual cool
app grey, and the only strong black on screen is the notation itself.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

FONT_UI = '"Segoe UI Variable Text", "Segoe UI", sans-serif'
FONT_MONO = '"Cascadia Mono", Consolas, monospace'


@dataclass(frozen=True)
class Palette:
    name: str
    app: str          # window background
    panel: str        # side panel, toolbar
    canvas: str       # backdrop the pages sit on
    paper: str        # the page itself
    on_paper: str     # words printed on the page
    border: str
    border_strong: str
    text: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_soft: str  # selection background
    on_accent: str    # text and icons on a full accent
    warn: str
    warn_soft: str
    danger: str
    danger_soft: str
    shadow: str
    font_ui: str = FONT_UI
    font_mono: str = FONT_MONO


LIGHT = Palette(
    name="light",
    app="#F3F3F1",
    panel="#FAFAF8",
    canvas="#5A5E66",
    paper="#FFFFFF",
    on_paper="#55554F",
    border="#D9D8D4",
    border_strong="#BFBEB9",
    text="#1A1A19",
    text_muted="#6A6A66",
    accent="#23459B",
    accent_hover="#1B3780",
    accent_soft="#E4E9F6",
    on_accent="#FFFFFF",
    warn="#7D5F0E",
    warn_soft="#F6EFD9",
    danger="#9B2C22",
    danger_soft="#F7E6E3",
    shadow="#3C3F45",
)

DARK = Palette(
    name="dark",
    app="#1E1E1D",
    panel="#252523",
    canvas="#141413",
    paper="#FFFFFF",
    on_paper="#55554F",
    border="#35342F",
    border_strong="#4A4842",
    text="#EAE9E6",
    text_muted="#9A9892",
    accent="#7E9BE6",
    accent_hover="#98AFEC",
    accent_soft="#26304A",
    on_accent="#111A30",
    warn="#D6B25E",
    warn_soft="#3A3220",
    danger="#E08376",
    danger_soft="#3A2420",
    shadow="#000000",
)


def palette_for(dark: bool) -> Palette:
    return DARK if dark else LIGHT


def system_prefers_dark() -> bool:
    """Follow the Windows app colour setting, falling back to light."""
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication

        hints = QGuiApplication.styleHints()
        scheme = getattr(hints, "colorScheme", None)
        if scheme is not None:
            return scheme() == Qt.ColorScheme.Dark
    except Exception:  # pragma: no cover - depends on the Qt build
        pass
    try:
        from PySide6.QtCore import QSettings

        key = (
            r"HKEY_CURRENT_USER\Software\Microsoft\Windows"
            r"\CurrentVersion\Themes\Personalize"
        )
        value = QSettings(key, QSettings.NativeFormat).value("AppsUseLightTheme")
        if value is not None:
            return int(value) == 0
    except Exception:  # pragma: no cover - no registry outside Windows
        pass
    return False


def font_families(stack: str) -> list[str]:
    """A CSS font stack as the list of families QFont falls back through."""
    return [name.strip().strip('"') for name in stack.split(",")]


def tokens(palette: Palette) -> dict[str, str]:
    return {field.name: getattr(palette, field.name) for field in fields(Palette)}


def stylesheet(palette: Palette) -> str:
    """Flat, native-feeling Qt styling. No gradients, no glass, no pills."""
    return _QSS.format(**tokens(palette))


_QSS = """
QWidget {{
    background: {app};
    color: {text};
    font-family: {font_ui};
    font-size: 10pt;
}}

QLabel {{
    background: transparent;
}}

QLabel#Heading {{
    font-size: 11pt;
    font-weight: 600;
}}
QLabel#Muted, QLabel#StatusText {{
    color: {text_muted};
}}
QLabel#EmptyState {{
    color: {text_muted};
}}
QLabel#Numeric {{
    font-family: {font_mono};
    color: {text_muted};
}}

/* --- panels ------------------------------------------------------- */

QWidget#SidePanel {{
    background: {panel};
    border-right: 1px solid {border};
}}
QWidget#SidePanel QStackedWidget {{
    background: {panel};
}}
QWidget#Toolbar {{
    background: {panel};
    border-bottom: 1px solid {border};
}}
QWidget#StatusBar {{
    background: {panel};
    border-top: 1px solid {border};
}}
QWidget#ZoomBar {{
    background: {panel};
    border-top: 1px solid {border};
}}

/* --- buttons ------------------------------------------------------ */

QPushButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 6px 10px;
    color: {text};
    text-align: left;
}}
QPushButton:hover {{
    background: {accent_soft};
}}
QPushButton:pressed {{
    background: {accent_soft};
    border-color: {border_strong};
}}
QPushButton:disabled {{
    color: {text_muted};
    background: transparent;
}}

QPushButton#Primary {{
    background: {accent};
    color: {on_accent};
    border: 1px solid {accent};
    padding: 7px 14px;
    text-align: center;
    font-weight: 600;
}}
QPushButton#Primary:hover {{
    background: {accent_hover};
    border-color: {accent_hover};
}}
QPushButton#Primary:disabled {{
    background: transparent;
    color: {text_muted};
    border: 1px solid {border};
}}

QPushButton#Quiet {{
    border: 1px solid {border};
    text-align: center;
}}
QPushButton#Quiet:checked {{
    background: {accent_soft};
    border-color: {accent};
    color: {accent};
}}
QPushButton#Quiet:hover {{
    border-color: {border_strong};
    background: {accent_soft};
}}

/* After every other state: each of them sets the border as well. A focus
   a keyboard user cannot see is no focus at all. Two pixels with a pixel less
   padding, so that tabbing through the toolbar moves nothing. */
QPushButton:focus {{
    border: 2px solid {accent};
    padding: 5px 9px;
}}
QPushButton#Primary:focus {{
    border: 2px solid {text};
    padding: 6px 13px;
}}
QPushButton#Quiet:focus {{
    border: 2px solid {accent};
    padding: 5px 9px;
}}

/* Qt leaves the width of the menu arrow out of the button's size, and the
   arrow then covers the end of the label. */
QPushButton#Quiet[menu="true"] {{
    padding-right: 26px;
}}
QPushButton#Quiet[menu="true"]:focus {{
    padding-right: 25px;
}}
QPushButton#Quiet::menu-indicator {{
    subcontrol-position: right center;
    right: 8px;
}}

/* Dialog buttons are ordinary buttons, not toolbar entries. */
QDialogButtonBox QPushButton {{
    border: 1px solid {border_strong};
    text-align: center;
    min-width: 76px;
}}
QDialogButtonBox QPushButton:default {{
    background: {accent};
    border-color: {accent};
    color: {on_accent};
    font-weight: 600;
}}
QDialogButtonBox QPushButton:default:hover {{
    background: {accent_hover};
}}
QDialogButtonBox QPushButton:default:focus {{
    border: 2px solid {text};
    padding: 5px 9px;
}}

/* --- shot list ---------------------------------------------------- */

QListWidget {{
    background: {panel};
    border: none;
    outline: none;
}}
QListWidget::item {{
    border-bottom: 1px solid {border};
}}
QListWidget::item:selected {{
    background: {accent_soft};
    color: {text};
}}

/* --- preview ------------------------------------------------------ */

QScrollArea#Preview {{
    background: {canvas};
    border: none;
}}
QWidget#PreviewCanvas {{
    background: {canvas};
}}
QLabel#PageSheet {{
    /* The sheet reads as paper: a hairline edge, never a floating rectangle. */
    border: 1px solid {shadow};
}}
QLabel#PageNumber {{
    color: {paper};
    font-family: {font_mono};
    font-size: 8pt;
}}
QLabel#BlankSheet {{
    background: {paper};
    color: {on_paper};
    border: 1px solid {shadow};
    padding: 40px;
    font-size: 11pt;
}}
QFrame#CaptureMark {{
    background: transparent;
    border: 2px solid {accent};
}}

/* --- inputs ------------------------------------------------------- */

QLineEdit, QDoubleSpinBox, QSpinBox {{
    background: {panel};
    border: 1px solid {border_strong};
    border-radius: 4px;
    padding: 5px 7px;
    selection-background-color: {accent};
    selection-color: {on_accent};
}}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
    border-color: {accent};
}}
QGroupBox {{
    border: none;
    font-weight: 600;
    margin-top: 20px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 0;
    top: 0;
}}
QGroupBox QLabel, QGroupBox QCheckBox {{
    font-weight: 400;
}}
QCheckBox {{
    spacing: 8px;
}}
QCheckBox:focus {{
    color: {accent};
}}

QSlider::groove:horizontal {{
    height: 3px;
    background: {border_strong};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {accent};
    width: 12px;
    height: 12px;
    margin: -5px 0;
    border-radius: 6px;
}}
QSlider::handle:horizontal:focus {{
    background: {text};
}}

/* --- scrollbars --------------------------------------------------- */

QScrollBar:vertical, QScrollBar:horizontal {{
    background: transparent;
    width: 12px;
    height: 12px;
    margin: 0;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {border_strong};
    border-radius: 6px;
    min-height: 32px;
    min-width: 32px;
}}
QScrollBar::handle:hover {{
    background: {text_muted};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

QSplitter::handle {{
    background: {border};
    width: 1px;
}}

/* --- menus and the series bar -------------------------------------- */

QMenu {{
    background: {panel};
    border: 1px solid {border_strong};
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 16px;
    border-radius: 3px;
}}
QMenu::item:selected {{
    background: {accent_soft};
}}
QMenu::item:disabled {{
    color: {text_muted};
    background: transparent;
}}
QMenu::separator {{
    height: 1px;
    background: {border};
    margin: 4px 6px;
}}

QWidget#SeriesBar {{
    background: {panel};
    border: 1px solid {border_strong};
    border-radius: 4px;
}}
QLabel#SeriesThumb {{
    background: {paper};
    border: 1px solid {border};
}}

QToolTip {{
    background: {panel};
    color: {text};
    border: 1px solid {border_strong};
    padding: 4px 6px;
}}
"""
