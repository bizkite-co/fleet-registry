import json
from pathlib import Path

import pytest

from fleet_registry.core import inventory as inv
from fleet_registry.core.audit import parse_audit_output
from fleet_registry.core.config import resolve_inventory_path
from fleet_registry.core.reconcile import diff, reconcile

ROOT = Path(__file__).resolve().parents[1]
DEVICES = ROOT / "inventory" / "devices.json"
FIXTURE = (Path(__file__).parent / "fixtures" / "nuc02_audit.txt").read_text(encoding="utf-8")

# The real inventory lives only in the git checkout, never in the sdist.
pytestmark = pytest.mark.skipif(not DEVICES.exists(), reason="needs repo inventory")


def test_round_trip_preserves_file(tmp_path: Path) -> None:
    data = inv.load(DEVICES)
    out = tmp_path / "devices.json"
    inv.save(data, out, touch=False)
    assert json.loads(out.read_text(encoding="utf-8")) == json.loads(
        DEVICES.read_text(encoding="utf-8")
    )


def test_find_is_case_insensitive() -> None:
    data = inv.load(DEVICES)
    device = data.find("NUC02")
    assert device is not None and device.id == "nuc02"


def test_template_devices_are_not_addressable() -> None:
    data = inv.load(DEVICES)
    assert [d.id for d in data.devices if d.is_addressable] == ["nuc01", "nuc02"]


def test_reconcile_only_touches_measured_fields(tmp_path: Path) -> None:
    data = inv.load(DEVICES)
    result = parse_audit_output("nuc02", FIXTURE)
    before = data.find("nuc02").model_copy(deep=True)  # type: ignore[union-attr]
    changes = {c.path for c in diff(before, result)}
    # The fixture matches the inventory except for the CPU string lscpu reports.
    assert changes == {"specs.cpu"}

    reconcile(data, "nuc02", result)
    after = data.find("nuc02")
    assert after is not None
    assert after.specs.cpu == "13th Gen Intel(R) Core(TM) i5-1340P"
    assert after.specs.storage == before.specs.storage  # free text untouched


def test_reconcile_adds_new_node() -> None:
    data = inv.load(DEVICES)
    result = parse_audit_output("nuc03", FIXTURE)
    device, changes = reconcile(data, "nuc03", result, add_missing=True)
    assert device is not None and data.find("nuc03") is device
    assert device.network.lan_ip == "10.0.0.10"
    saved = json.loads(inv.dumps(data))
    assert saved["devices"][-1]["specs"]["threads"] == 16


def test_resolve_inventory_walks_up(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("FLEET_REGISTRY_INVENTORY", raising=False)
    nested = ROOT / "docs"
    assert resolve_inventory_path(cwd=nested, config={}) == DEVICES
