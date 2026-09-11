"""Single source of the version at runtime.

A PyInstaller bundle ships no dist-info, so importlib.metadata cannot answer
this. release-please keeps the literal below in step with pyproject.toml.
"""

__version__ = "0.2.0"  # x-release-please-version
