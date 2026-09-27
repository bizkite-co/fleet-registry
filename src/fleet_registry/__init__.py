"""Inventory, audit, and provisioning for a homelab fleet of Linux nodes."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("fleet-registry")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0"

PACKAGE_NAME = "fleet-registry"
