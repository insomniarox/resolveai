"""ResolveAI investigation application."""

from importlib.metadata import PackageNotFoundError, version

try:
    APPLICATION_VERSION = version("resolveai")
except PackageNotFoundError:
    APPLICATION_VERSION = "0.0.0+uninstalled"
