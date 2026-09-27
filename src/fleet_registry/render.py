"""Rich renderables shared by the CLI and TUI, styled with the verkit theme."""

from __future__ import annotations

from typing import Any

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text
from verkit.theme import DEFAULT as theme

from fleet_registry.core.audit import AuditResult
from fleet_registry.core.models import Device
from fleet_registry.core.reconcile import FieldChange

STATUS_STYLES = {"online": "green", "offline": "red", "pending": "yellow", "unboxed": "yellow"}


def table(title: str | None = None, **kwargs: Any) -> Table:
    return Table(
        title=title,
        title_justify="left",
        box=theme.table_box,
        header_style=theme.header_style,
        padding=theme.table_padding,
        **kwargs,
    )


def _v(value: Any) -> str:
    return "—" if value is None or value == "" else str(value)


def status_text(status: str | None) -> Text:
    return Text(_v(status), style=STATUS_STYLES.get((status or "").lower(), ""))


def reach_text(reachable: bool | None) -> Text:
    if reachable is None:
        return Text("—", style="dim")
    return Text("up", style="green") if reachable else Text("down", style="red")


def fleet_table(devices: list[Device], reach: dict[str, bool] | None = None) -> Table:
    t = table()
    for col in ("ID", "Hostname", "Model", "CPU", "RAM", "Tailscale IP", "Status"):
        t.add_column(col, no_wrap=col != "Model")
    if reach is not None:
        t.add_column("SSH")
    for d in devices:
        cores = f"{_v(d.specs.cores)}c/{_v(d.specs.threads)}t" if d.specs.cores else "—"
        ram = f"{d.specs.ram_total_gb} GB" if d.specs.ram_total_gb else "—"
        row: list[RenderableType] = [
            Text(d.id, style="bold"),
            _v(d.hostname),
            _v(d.model),
            cores,
            ram,
            _v(d.network.tailscale_ip),
            status_text(d.status),
        ]
        if reach is not None:
            row.append(reach_text(reach.get(d.id)))
        t.add_row(*row)
    return t


def _kv(title: str, pairs: dict[str, Any]) -> Table:
    t = table(title)
    t.add_column("Field", style="dim")
    t.add_column("Value")
    for k, v in pairs.items():
        t.add_row(k, _v(v))
    return t


def device_detail(d: Device) -> RenderableType:
    return Group(
        _kv(
            f"{d.id}",
            {
                "hostname": d.hostname,
                "ssh target": d.ssh_target,
                "type / arch": f"{_v(d.device_type)} / {_v(d.architecture)}",
                "model": d.model,
                "chassis": d.chassis,
                "role": d.role,
                "status": d.status,
            },
        ),
        Text(),
        _kv("specs", d.specs.model_dump()),
        Text(),
        _kv("network", d.network.model_dump()),
        Text(),
        _kv("os", d.os.model_dump()),
    )


def audit_detail(r: AuditResult) -> RenderableType:
    slots = f"{_v(r.ram_slots_used)}/{_v(r.ram_slots_total)} slots"
    summary = _kv(
        f"audit: {r.node} @ {r.collected_at}",
        {
            "hostname": r.hostname,
            "cpu": r.cpu_model,
            "cores / threads": f"{_v(r.cores)} / {_v(r.threads)}",
            "max MHz": r.max_mhz,
            "RAM": f"{_v(r.ram_total_gb)} GB ({slots})",
            "LAN": f"{_v(r.lan_ip)} on {_v(r.primary_interface)} ({_v(r.mac_ethernet)})",
            "tailscale": f"{_v(r.tailscale_ip)}  {_v(r.tailscale_fqdn)}",
            "os": r.os_pretty_name,
            "kernel": r.kernel,
        },
    )
    parts: list[RenderableType] = [summary]
    if r.dimms:
        t = table("memory")
        for col in ("Slot", "Size", "Type", "Speed", "Part"):
            t.add_column(col)
        for m in r.dimms:
            t.add_row(
                _v(m.locator),
                f"{m.size_gb:g} GB" if m.size_gb else "—",
                _v(m.type),
                _v(m.speed),
                f"{_v(m.manufacturer)} {m.part_number or ''}".strip(),
            )
        parts += [Text(), t]
    if r.disks:
        t = table("disks")
        for col in ("Name", "Size", "Model", "Bus"):
            t.add_column(col)
        for disk in r.disks:
            t.add_row(disk.name, f"{_v(disk.size_gb)} GB", _v(disk.model), _v(disk.transport))
        parts += [Text(), t]
    for w in r.warnings:
        parts.append(Text(f"! {w}", style="yellow"))
    return Group(*parts)


def changes_table(changes: list[FieldChange], title: str = "inventory changes") -> RenderableType:
    if not changes:
        return Text("Inventory already matches the audit.", style="green")
    t = table(title)
    t.add_column("Field")
    t.add_column("Inventory", style="red")
    t.add_column("Audit", style="green")
    for c in changes:
        t.add_row(c.path, _v(c.old), _v(c.new))
    return t
