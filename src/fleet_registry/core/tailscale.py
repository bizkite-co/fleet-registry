"""Discover fleet candidates from the local Tailscale client's view of the tailnet."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from fleet_registry.core import FleetError
from fleet_registry.core.models import Device, Inventory
from fleet_registry.core.ssh import is_wsl

ENV_TAILSCALE = "FLEET_TAILSCALE"
_NEVER = "0001-01-01T00:00:00Z"


class TailscaleError(FleetError):
    pass


class TailnetNode(BaseModel):
    hostname: str
    dns_name: str | None = None
    ip: str | None = None
    os: str | None = None
    online: bool = False
    last_seen: str | None = None
    tags: list[str] = Field(default_factory=list)
    is_self: bool = False
    is_local: bool = False  # another tailscaled on this machine, e.g. inside WSL

    @property
    def name(self) -> str:
        """MagicDNS short name: unique on the tailnet and usable as an SSH host."""
        return self.dns_name.split(".")[0] if self.dns_name else self.hostname.lower()

    @property
    def is_fleet_candidate(self) -> bool:
        """Linux nodes that aren't this machine (or its WSL) are potential fleet members."""
        return self.os == "linux" and not (self.is_self or self.is_local)


def _candidates() -> list[str]:
    if env := os.environ.get(ENV_TAILSCALE):
        return [env]
    found = [p for p in (shutil.which("tailscale"),) if p]
    if sys.platform == "win32":
        found.append(r"C:\Program Files\Tailscale\tailscale.exe")
    elif is_wsl():
        # WSL usually has no tailscaled of its own; ask the Windows client.
        found += [
            p
            for p in (shutil.which("tailscale.exe"), "/mnt/c/Program Files/Tailscale/tailscale.exe")
            if p
        ]
    return [p for p in dict.fromkeys(found) if Path(p).exists() or shutil.which(p)]


def status_json() -> dict[str, Any]:
    errors = []
    for exe in _candidates():
        try:
            proc = subprocess.run(
                [exe, "status", "--json"], capture_output=True, timeout=15, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            errors.append(f"{exe}: {e}")
            continue
        if proc.returncode == 0:
            try:
                data = json.loads(proc.stdout.decode("utf-8", errors="replace"))
            except json.JSONDecodeError as e:
                errors.append(f"{exe}: bad JSON: {e}")
                continue
            if isinstance(data, dict):
                return data
        errors.append(f"{exe}: {proc.stderr.decode(errors='replace').strip() or 'failed'}")
    detail = "; ".join(errors) or "no tailscale client found"
    raise TailscaleError(f"Could not read tailnet status ({detail}). Set ${ENV_TAILSCALE}.")


def _node(raw: dict[str, Any], is_self: bool) -> TailnetNode:
    ips = raw.get("TailscaleIPs") or []
    last_seen = raw.get("LastSeen")
    return TailnetNode(
        hostname=raw.get("HostName") or "?",
        dns_name=(raw.get("DNSName") or "").rstrip(".") or None,
        ip=next((ip for ip in ips if "." in ip), None),
        os=raw.get("OS") or None,
        online=bool(raw.get("Online")) or is_self,
        last_seen=None if last_seen in (None, _NEVER) else last_seen,
        tags=list(raw.get("Tags") or []),
        is_self=is_self,
    )


def parse_status(data: dict[str, Any]) -> list[TailnetNode]:
    nodes = []
    if isinstance(data.get("Self"), dict):
        nodes.append(_node(data["Self"], is_self=True))
    nodes += [_node(p, is_self=False) for p in (data.get("Peer") or {}).values()]
    me = next((n.hostname.lower() for n in nodes if n.is_self), None)
    for n in nodes:
        n.is_local = not n.is_self and n.hostname.lower() == me
    return sorted(nodes, key=lambda n: n.name)


def tailnet_nodes() -> list[TailnetNode]:
    return parse_status(status_json())


def match_device(inventory: Inventory, node: TailnetNode) -> Device | None:
    """The inventory device for a tailnet node, matched by Tailscale IP, FQDN, or name."""
    for d in inventory.devices:
        if node.ip and d.network.tailscale_ip == node.ip:
            return d
        if node.dns_name and d.network.tailscale_fqdn == node.dns_name:
            return d
    return inventory.find(node.name) or inventory.find(node.hostname)
