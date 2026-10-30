"""A one-line label that shortens its text instead of widening the window."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAccessible, QAccessibleEvent, QPainter
from PySide6.QtWidgets import QLabel


class ElidedLabel(QLabel):
    """Keeps the whole text in `text()` and in a tooltip once it is cut.

    A plain QLabel asks for its full width, so one exported path in the status
    line could push the window past the edge of the screen.
    """

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt naming)
        return QSize(0, super().minimumSizeHint().height())

    def setText(self, text: str) -> None:  # noqa: N802 (Qt naming)
        super().setText(text)
        self._refresh_tooltip()
        # Nothing else tells a screen reader that the status line moved on.
        QAccessible.updateAccessibility(
            QAccessibleEvent(self, QAccessible.Event.NameChanged)
        )

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self._refresh_tooltip()

    def shown_text(self) -> str:
        """The text as it fits, with the middle given up rather than the end.

        The end of a status line is what the user waits for.
        """
        return self.fontMetrics().elidedText(
            self.text(), Qt.TextElideMode.ElideMiddle, self.contentsRect().width()
        )

    def _refresh_tooltip(self) -> None:
        self.setToolTip(self.text() if self.shown_text() != self.text() else "")

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        self.style().drawItemText(
            painter,
            self.contentsRect(),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.palette(),
            self.isEnabled(),
            self.shown_text(),
            self.foregroundRole(),
        )
