"""Collect hardware / network / OS facts from a node and parse them into typed data.

One SSH round trip runs ``REMOTE_SCRIPT``, which prints ``@@@<section>`` markers
followed by (mostly JSON) command output. Parsing is pure and unit-tested
against captured fixtures.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from fleet_registry.core import FleetError
from fleet_registry.core.ssh import run_script

REMOTE_SCRIPT = r"""
sec() { printf '\n@@@%s\n' "$1"; }
sec hostname;   hostname
sec arch;       dpkg --print-architecture 2>/dev/null || uname -m
sec model;      tr -d '\0' </proc/device-tree/model 2>/dev/null \
                || cat /sys/class/dmi/id/product_name 2>/dev/null
sec lscpu;      lscpu -J 2>/dev/null
sec meminfo;    grep MemTotal /proc/meminfo
sec dmidecode;  sudo -n dmidecode -t memory 2>/dev/null
sec lsblk;      lsblk -J -d -b -o NAME,SIZE,TYPE,MODEL,TRAN 2>/dev/null
sec ip_addr;    ip -j addr 2>/dev/null
sec ip_route;   ip -j route get 1.1.1.1 2>/dev/null
sec tailscale;  tailscale status --json 2>/dev/null
sec os_release; cat /etc/os-release 2>/dev/null
sec kernel;     uname -r
sec end
exit 0
"""

_SECTION_RE = re.compile(r"^@@@(\w+)$", re.MULTILINE)
_GIB = 1024**3


class AuditError(FleetError):
    pass


class Dimm(BaseModel):
    locator: str | None = None
    size_gb: float | None = None
    type: str | None = None
    speed: str | None = None
    manufacturer: str | None = None
    part_number: str | None = None


class Disk(BaseModel):
    name: str
    size_bytes: int | None = None
    model: str | None = None
    transport: str | None = None

    @property
    def size_gb(self) -> float | None:
        return round(self.size_bytes / 1e9) if self.size_bytes else None


class Interface(BaseModel):
    name: str
    mac: str | None = None
    ipv4: list[str] = Field(default_factory=list)
    state: str | None = None


def device_type_for(hardware_model: str | None) -> str | None:
    m = (hardware_model or "").lower()
    if "raspberry pi" in m:
        return "raspberry-pi"
    if "nuc" in m:
        return "nuc"
    return None


class AuditResult(BaseModel):
    node: str
    collected_at: str
    hostname: str | None = None
    architecture: str | None = None
    hardware_model: str | None = None
    cpu_model: str | None = None
    cores: int | None = None
    threads: int | None = None
    max_mhz: int | None = None
    ram_total_gb: int | float | None = None
    ram_slots_total: int | None = None
    ram_slots_used: int | None = None
    dimms: list[Dimm] = Field(default_factory=list)
    disks: list[Disk] = Field(default_factory=list)
    interfaces: list[Interface] = Field(default_factory=list)
    primary_interface: str | None = None
    lan_ip: str | None = None
    mac_ethernet: str | None = None
    tailscale_ip: str | None = None
    tailscale_fqdn: str | None = None
    os_pretty_name: str | None = None
    kernel: str | None = None
    warnings: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- parsing


def split_sections(text: str) -> dict[str, str]:
    text = text.replace("\r\n", "\n")
    parts = _SECTION_RE.split(text)
    # parts = [preamble, name1, body1, name2, body2, ...]
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def _load_json(body: str) -> Any:
    try:
        return json.loads(body) if body else None
    except json.JSONDecodeError:
        return None


def _flatten_lscpu(entries: list[dict[str, Any]]) -> dict[str, str]:
    """lscpu -J nests fields under ``children`` on util-linux >= 2.38."""
    flat: dict[str, str] = {}
    for entry in entries:
        key = str(entry.get("field", "")).rstrip(":").strip()
        if key and key not in flat and entry.get("data") is not None:
            flat[key] = str(entry["data"])
        flat.update(
            {k: v for k, v in _flatten_lscpu(entry.get("children", [])).items() if k not in flat}
        )
    return flat


def _int(value: str | None) -> int | None:
    try:
        return int(float(value)) if value is not None else None
    except ValueError:
        return None


def _whole(value: float) -> int | float:
    return int(value) if float(value).is_integer() else round(value, 1)


def parse_lscpu(body: str) -> dict[str, Any]:
    data = _load_json(body)
    if not isinstance(data, dict):
        return {}
    f = _flatten_lscpu(data.get("lscpu", []))
    per_socket = _int(f.get("Core(s) per socket") or f.get("Core(s) per cluster"))
    sockets = _int(f.get("Socket(s)") or f.get("Cluster(s)")) or 1
    return {
        "cpu_model": f.get("Model name"),
        "cores": per_socket * sockets if per_socket else None,
        "threads": _int(f.get("CPU(s)")),
        "max_mhz": _int(f.get("CPU max MHz")),
    }


def parse_dmidecode(body: str) -> list[Dimm | None]:
    """Return one entry per memory slot: a ``Dimm`` if populated, else ``None``."""
    slots: list[Dimm | None] = []
    for block in re.split(r"\n(?=Memory Device\n)", body):
        if not block.startswith("Memory Device"):
            continue
        fields: dict[str, str] = {}
        for line in block.splitlines()[1:]:
            if ":" in line and line.startswith("\t") and not line.startswith("\t\t"):
                k, _, v = line.strip().partition(":")
                fields[k.strip()] = v.strip()
        size = fields.get("Size", "")
        m = re.match(r"(\d+)\s*(GB|MB|TB)", size)
        if not m:
            slots.append(None)
            continue
        n, unit = int(m.group(1)), m.group(2)
        size_gb = n / 1024 if unit == "MB" else n * 1024 if unit == "TB" else n
        slots.append(
            Dimm(
                locator=fields.get("Locator"),
                size_gb=size_gb,
                type=fields.get("Type"),
                speed=fields.get("Speed") or fields.get("Configured Memory Speed"),
                manufacturer=fields.get("Manufacturer"),
                part_number=(fields.get("Part Number") or "").strip() or None,
            )
        )
    return slots


def parse_lsblk(body: str) -> list[Disk]:
    data = _load_json(body)
    if not isinstance(data, dict):
        return []
    disks = []
    for dev in data.get("blockdevices", []):
        if dev.get("type") != "disk" or str(dev.get("name", "")).startswith(("zram", "loop")):
            continue
        disks.append(
            Disk(
                name=dev["name"],
                size_bytes=_int(dev.get("size")),
                model=(dev.get("model") or "").strip() or None,
                transport=dev.get("tran"),
            )
        )
    return disks


def parse_ip_addr(body: str) -> list[Interface]:
    data = _load_json(body)
    if not isinstance(data, list):
        return []
    out = []
    for link in data:
        if link.get("link_type") == "loopback":
            continue
        out.append(
            Interface(
                name=link.get("ifname", "?"),
                mac=(link.get("address") or "").upper() or None,
                ipv4=[a["local"] for a in link.get("addr_info", []) if a.get("family") == "inet"],
                state=link.get("operstate"),
            )
        )
    return out


def parse_route(body: str) -> tuple[str | None, str | None]:
    """(device, source ip) of the default route."""
    data = _load_json(body)
    if isinstance(data, list) and data:
        return data[0].get("dev"), data[0].get("prefsrc")
    return None, None


def parse_tailscale(body: str) -> tuple[str | None, str | None]:
    data = _load_json(body)
    if not isinstance(data, dict) or not isinstance(data.get("Self"), dict):
        return None, None
    me = data["Self"]
    ipv4 = next((ip for ip in me.get("TailscaleIPs") or [] if "." in ip), None)
    fqdn = (me.get("DNSName") or "").rstrip(".") or None
    return ipv4, fqdn


def parse_os_release(body: str) -> str | None:
    m = re.search(r'^PRETTY_NAME="?([^"\n]*)"?', body, re.MULTILINE)
    return m.group(1) if m else None


def parse_audit_output(node: str, text: str) -> AuditResult:
    s = split_sections(text)
    if "end" not in s:
        raise AuditError(f"{node}: incomplete audit output (remote script did not finish)")
    warnings: list[str] = []

    cpu = parse_lscpu(s.get("lscpu", ""))
    if not cpu:
        warnings.append("lscpu -J unavailable; CPU facts missing")

    slots = parse_dmidecode(s.get("dmidecode", ""))
    dimms = [d for d in slots if d is not None]
    if slots and dimms:
        ram_total: int | float | None = _whole(sum(d.size_gb or 0 for d in dimms))
    else:
        # Boards without DMI tables (e.g. Raspberry Pi) have no slot data to read.
        if not slots and device_type_for(s.get("model")) != "raspberry-pi":
            warnings.append("dmidecode needs passwordless sudo; RAM slot details missing")
        m = re.search(r"(\d+)\s*kB", s.get("meminfo", ""))
        ram_total = round(int(m.group(1)) * 1024 / _GIB) if m else None

    interfaces = parse_ip_addr(s.get("ip_addr", ""))
    dev, src = parse_route(s.get("ip_route", ""))
    primary = next((i for i in interfaces if i.name == dev), None)
    ts_ip, ts_fqdn = parse_tailscale(s.get("tailscale", ""))
    if ts_ip is None:
        warnings.append("tailscale not running or not installed")

    return AuditResult(
        node=node,
        collected_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        hostname=s.get("hostname") or None,
        architecture=s.get("arch") or None,
        hardware_model=s.get("model") or None,
        cpu_model=cpu.get("cpu_model"),
        cores=cpu.get("cores"),
        threads=cpu.get("threads"),
        max_mhz=cpu.get("max_mhz"),
        ram_total_gb=ram_total,
        ram_slots_total=len(slots) or None,
        ram_slots_used=len(dimms) if slots else None,
        dimms=dimms,
        disks=parse_lsblk(s.get("lsblk", "")),
        interfaces=interfaces,
        primary_interface=dev,
        lan_ip=src or (primary.ipv4[0] if primary and primary.ipv4 else None),
        mac_ethernet=primary.mac if primary else None,
        tailscale_ip=ts_ip,
        tailscale_fqdn=ts_fqdn,
        os_pretty_name=parse_os_release(s.get("os_release", "")),
        kernel=s.get("kernel") or None,
        warnings=warnings,
    )


# --------------------------------------------------------------------------- running


async def audit_node(host: str, *, timeout: float = 60) -> AuditResult:
    result = await run_script(host, REMOTE_SCRIPT, timeout=timeout)
    if result.returncode == 255:
        lines = [ln.strip() for ln in result.stderr.splitlines() if ln.strip()]
        raise AuditError(f"{host}: ssh failed: {'; '.join(lines) or 'connection failed'}")
    return parse_audit_output(host, result.stdout)


async def audit_many(hosts: list[str]) -> dict[str, AuditResult | BaseException]:
    results = await asyncio.gather(*(audit_node(h) for h in hosts), return_exceptions=True)
    return dict(zip(hosts, results, strict=True))
