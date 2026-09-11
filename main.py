"""PyInstaller entry script.

PyInstaller needs a plain script, and the package's own modules use relative
imports that only resolve as part of the package.
"""

from scorecap.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
