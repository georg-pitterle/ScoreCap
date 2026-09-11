"""Icons drawn from Segoe Fluent Icons, the symbol font Windows 11 ships.

Using the system font keeps the toolbar native and adds no image assets. On
a machine without the font, `available()` is False and callers fall back to
plain labels rather than rendering tofu boxes.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap

FONT_FAMILY = "Segoe Fluent Icons"
LEGACY_FAMILY = "Segoe MDL2 Assets"

# Glyph names say what the button does, not what the glyph is called.
CAPTURE = ""      # crop marks
RECAPTURE = ""    # refresh
CROP = ""
DELETE = ""
SETTINGS = ""
EXPORT = ""       # save
UNDO = ""
ZOOM_FIT = ""
ZOOM_IN = ""
ZOOM_OUT = ""
WARNING = ""
MISSING = ""


def _families() -> set[str]:
    return set(QFontDatabase.families())


def available() -> bool:
    return bool({FONT_FAMILY, LEGACY_FAMILY} & _families())


def icon_font(size: int) -> QFont:
    families = _families()
    family = FONT_FAMILY if FONT_FAMILY in families else LEGACY_FAMILY
    font = QFont(family)
    font.setPixelSize(size)
    return font


def icon(glyph: str, colour: str, size: int = 16) -> QIcon:
    """Render one glyph into an icon of the given colour."""
    scale = 2  # draw oversized so the icon stays crisp on HiDPI screens
    pixmap = QPixmap(QSize(size * scale, size * scale))
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setFont(icon_font(size * scale))
        painter.setPen(QColor(colour))
        painter.drawText(QRect(0, 0, size * scale, size * scale), Qt.AlignCenter, glyph)
    finally:
        painter.end()
    pixmap.setDevicePixelRatio(scale)
    return QIcon(pixmap)
