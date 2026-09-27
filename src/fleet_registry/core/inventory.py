"""Load and save the inventory file."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from fleet_registry.core import FleetError
from fleet_registry.core.models import Inventory


class InventoryError(FleetError):
    pass


def load(path: Path) -> Inventory:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise InventoryError(f"Inventory file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise InventoryError(f"{path} is not valid JSON: {e}") from e
    try:
        return Inventory.model_validate(raw)
    except ValidationError as e:
        raise InventoryError(f"{path} does not match the inventory schema:\n{e}") from e


def dumps(inventory: Inventory) -> str:
    return json.dumps(inventory.to_json_dict(), indent=2, ensure_ascii=False) + "\n"


def save(inventory: Inventory, path: Path, touch: bool = True) -> None:
    """Atomically write the inventory, stamping ``updated_at`` when ``touch`` is set."""
    if touch:
        inventory.updated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    text = dumps(inventory)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".devices.", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def json_schema() -> dict[str, object]:
    return Inventory.model_json_schema(by_alias=True)
