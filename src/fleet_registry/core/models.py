"""Pydantic models for ``inventory/devices.json``.

Models allow extra keys so hand-added fields survive a load/save round trip,
and inventory writes use ``exclude_unset`` so absent keys stay absent.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Specs(_Model):
    cpu: str | None = None
    cores: int | None = None
    threads: int | None = None
    max_turbo_mhz: int | None = None
    ram_total_gb: int | float | None = None
    ram_slots_used: int | None = None
    ram_slots_total: int | None = None
    ram_details: str | None = None
    storage: str | None = None
    sata_bay_occupied: bool | None = None


class Network(_Model):
    mac_ethernet: str | None = None
    nic_model: str | None = None
    lan_ip: str | None = None
    tailscale_ip: str | None = None
    tailscale_fqdn: str | None = None
    mdns_hostname: str | None = None


class OsInfo(_Model):
    distribution: str | None = None
    kernel: str | None = None
    user: str | None = None
    sudo: str | None = None
    ssh_key_auth: bool | None = None


class Device(_Model):
    id: str
    hostname: str | None = None
    ssh_host: str | None = Field(
        default=None,
        description="SSH target (host alias or address). Defaults to the device id.",
    )
    device_type: str | None = None
    architecture: str | None = None
    model: str | None = None
    chassis: str | None = None
    specs: Specs = Field(default_factory=Specs)
    network: Network = Field(default_factory=Network)
    os: OsInfo = Field(default_factory=OsInfo)
    status: str | None = None
    role: str | None = None

    @property
    def ssh_target(self) -> str:
        return self.ssh_host or self.id

    @property
    def is_addressable(self) -> bool:
        """True when the inventory records some way to reach this node.

        Template entries (e.g. ``pi-template``) have no addresses and are
        skipped by fleet-wide operations.
        """
        n = self.network
        return bool(
            self.ssh_host or n.tailscale_ip or n.tailscale_fqdn or n.lan_ip or n.mdns_hostname
        )


class Inventory(_Model):
    schema_ref: str | None = Field(default=None, alias="$schema")
    fleet_name: str = "Fleet"
    updated_at: str | None = None
    devices: list[Device] = Field(default_factory=list)

    def find(self, key: str) -> Device | None:
        """Look a device up by id, hostname, or ssh_host (case-insensitive)."""
        k = key.lower()
        for d in self.devices:
            if k in {d.id.lower(), (d.hostname or "").lower(), (d.ssh_host or "").lower()}:
                return d
        return None

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True, exclude_unset=True)
