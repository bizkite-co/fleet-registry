"""Compare an ``AuditResult`` with an inventory ``Device`` and apply the differences.

Only machine-measurable fields are reconciled. Hand-written descriptions
(``model``, ``storage``, ``ram_details``, ``nic_model``, ``role`` ...) are never
overwritten.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fleet_registry.core.audit import AuditResult
from fleet_registry.core.models import Device, Inventory


@dataclass(frozen=True)
class FieldChange:
    path: str  # "section.field" or "field"
    old: Any
    new: Any


def measured_values(r: AuditResult) -> dict[str, Any]:
    values = {
        "architecture": r.architecture,
        "specs.cpu": r.cpu_model,
        "specs.cores": r.cores,
        "specs.threads": r.threads,
        "specs.max_turbo_mhz": r.max_mhz,
        "specs.ram_total_gb": r.ram_total_gb,
        "specs.ram_slots_used": r.ram_slots_used,
        "specs.ram_slots_total": r.ram_slots_total,
        "network.mac_ethernet": r.mac_ethernet,
        "network.lan_ip": r.lan_ip,
        "network.tailscale_ip": r.tailscale_ip,
        "network.tailscale_fqdn": r.tailscale_fqdn,
        "os.distribution": r.os_pretty_name,
        "os.kernel": r.kernel,
    }
    return {k: v for k, v in values.items() if v is not None}


def _get(device: Device, path: str) -> Any:
    obj: Any = device
    for part in path.split("."):
        obj = getattr(obj, part, None)
    return obj


def diff(device: Device, result: AuditResult) -> list[FieldChange]:
    return [
        FieldChange(path, _get(device, path), new)
        for path, new in measured_values(result).items()
        if _get(device, path) != new
    ]


def apply(device: Device, changes: list[FieldChange]) -> None:
    for change in changes:
        section, _, field = change.path.rpartition(".")
        if section:
            sub = getattr(device, section)
            setattr(sub, field, change.new)
            # Mark the section as explicitly set so exclude_unset keeps it on save.
            setattr(device, section, sub)
        else:
            setattr(device, field, change.new)


def new_device(node: str, result: AuditResult) -> Device:
    """Build an inventory entry for a node that isn't registered yet."""
    device = Device(id=node, hostname=result.hostname, status="online")
    apply(device, diff(device, result))
    return device


def reconcile(
    inventory: Inventory, node: str, result: AuditResult, *, add_missing: bool = False
) -> tuple[Device | None, list[FieldChange]]:
    """Apply ``result`` to the matching device. Returns (device, changes applied).

    Unknown nodes are appended when ``add_missing`` is set, else left alone.
    """
    device = inventory.find(node)
    if device is None:
        if not add_missing:
            return None, []
        device = new_device(node, result)
        inventory.devices.append(device)
        return device, [FieldChange(p, None, v) for p, v in measured_values(result).items()]
    changes = diff(device, result)
    apply(device, changes)
    return device, changes
