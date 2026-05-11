"""aX Platform CLI."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("axctl")
except PackageNotFoundError:
    __version__ = "unknown"
