"""Locating the inventory file and user settings.

Inventory resolution order:
  1. an explicit path (``--inventory``)
  2. ``$FLEET_REGISTRY_INVENTORY``
  3. ``inventory/devices.json`` in the current directory or any parent
  4. ``inventory`` in the user config file (set with ``fr config --inventory``)
"""

from __future__ import annotations

import json
import os
import sys
import tomllib
from pathlib import Path
from typing import Any

from fleet_registry.core import FleetError

ENV_INVENTORY = "FLEET_REGISTRY_INVENTORY"
ENV_SSH = "FLEET_SSH"
INVENTORY_RELPATH = Path("inventory") / "devices.json"


class InventoryNotFound(FleetError):
    pass


def user_config_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "fleet-registry" / "config.toml"


def load_user_config(path: Path | None = None) -> dict[str, Any]:
    path = path or user_config_path()
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def save_user_config(values: dict[str, str], path: Path | None = None) -> Path:
    """Write flat string settings. JSON string escaping is valid TOML basic-string syntax."""
    path = path or user_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key} = {json.dumps(value)}" for key, value in sorted(values.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def find_inventory_upwards(start: Path) -> Path | None:
    for directory in (start, *start.parents):
        candidate = directory / INVENTORY_RELPATH
        if candidate.is_file():
            return candidate
    return None


def resolve_inventory_path(
    explicit: Path | None = None,
    cwd: Path | None = None,
    config: dict[str, Any] | None = None,
) -> Path:
    if explicit is not None:
        return explicit
    if env := os.environ.get(ENV_INVENTORY):
        return Path(env).expanduser()
    if found := find_inventory_upwards((cwd or Path.cwd()).resolve()):
        return found
    config = load_user_config() if config is None else config
    if configured := config.get("inventory"):
        return Path(configured).expanduser()
    raise InventoryNotFound(
        "No inventory found. Run from inside the fleet-registry checkout, pass --inventory, "
        f"set ${ENV_INVENTORY}, or run `fr config --inventory PATH`."
    )
