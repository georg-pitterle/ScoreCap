"""Entry point: python -m scorecap

Kept to a shim: PyInstaller skips modules named __main__, so the real work
lives in scorecap.cli where both the module run and the bundle can reach it.
"""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
