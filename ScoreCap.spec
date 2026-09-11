# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build. One directory, not one file: Velopack updates a folder,
and a one-file build would unpack over a hundred megabytes on every start."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs

# PySide6-Essentials still ships more than this app touches. Anything listed
# here is either an addon we never import or a stdlib corner pulled in by Pillow.
EXCLUDES = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtSpatialAudio",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtUiTools",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtSerialPort",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "tkinter",
    "unittest",
    "pytest",
]

# Qt drags along modules the bundle never loads. Dropping them after the
# analysis is the reliable way - excluding the Python module leaves the DLL.
DROP_BINARIES = (
    "qt6quick",
    "qt6qml",
    "qt6quickwidgets",
    "qt6pdf",
)
KEEP_TRANSLATIONS = ("_de.qm", "_en.qm")


def _keep_binary(entry) -> bool:
    name = Path(entry[0]).name.lower()
    return not name.startswith(DROP_BINARIES)


def _keep_data(entry) -> bool:
    dest = entry[0].replace("\\", "/").lower()
    if "/translations/" not in dest:
        return True
    return dest.endswith(KEEP_TRANSLATIONS)


a = Analysis(
    ["main.py"],
    # An editable install resolves through a finder hook PyInstaller cannot
    # follow, so point it at the source tree directly.
    pathex=[SPECPATH],
    binaries=collect_dynamic_libs("velopack"),
    datas=[("assets/scorecap.ico", "assets")],
    hiddenimports=["velopack", "scorecap.cli"],
    excludes=EXCLUDES,
    noarchive=False,
)

a.binaries = [entry for entry in a.binaries if _keep_binary(entry)]
a.datas = [entry for entry in a.datas if _keep_data(entry)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ScoreCap",
    console=False,
    icon="assets/scorecap.ico",
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ScoreCap",
)
