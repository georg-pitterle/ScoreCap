"""The question a project file raises: may the current captures be dropped?"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QMessageBox, QPushButton, QWidget

from .project import SUFFIX


def project_filter() -> str:
    """The file dialog filter for ScoreCap projects."""
    return QCoreApplication.translate(
        "MainWindow", "ScoreCap project (*{suffix})"
    ).format(suffix=SUFFIX)


def unsaved_changes_box(
    parent: QWidget,
) -> tuple[QMessageBox, QPushButton, QPushButton]:
    """The box asking about unsaved captures, with its save and discard buttons."""
    # Every text spelled out in its own translate() call: pyside6-lupdate
    # only collects texts that stand there as literals.
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(QCoreApplication.translate("MainWindow", "Unsaved captures"))
    box.setText(
        QCoreApplication.translate("MainWindow", "The captures have not been saved.")
    )
    box.setInformativeText(
        QCoreApplication.translate(
            "MainWindow", "Unsaved captures are lost when ScoreCap closes."
        )
    )
    save = box.addButton(
        QCoreApplication.translate("MainWindow", "Save"),
        QMessageBox.ButtonRole.AcceptRole,
    )
    discard = box.addButton(
        QCoreApplication.translate("MainWindow", "Don't save"),
        QMessageBox.ButtonRole.DestructiveRole,
    )
    box.addButton(
        QCoreApplication.translate("MainWindow", "Cancel"),
        QMessageBox.ButtonRole.RejectRole,
    )
    box.setDefaultButton(save)
    # The message box sizes its buttons before the window's stylesheet has
    # styled them, and the stylesheet's larger font then cut the German
    # "Nicht speichern" off. Styling them first fixes the widths.
    for button in box.buttons():
        button.ensurePolished()
        button.setMinimumWidth(button.sizeHint().width())
    return box, save, discard


def ask_save_changes(parent: QWidget) -> str:
    """'save', 'discard' or 'cancel' for unsaved work."""
    box, save, discard = unsaved_changes_box(parent)
    box.exec()
    clicked = box.clickedButton()
    if clicked is save:
        return "save"
    if clicked is discard:
        return "discard"
    return "cancel"
