from pathlib import Path

import pytest

from fleet_registry.core.audit import AuditError, parse_audit_output, split_sections

FIXTURE = (Path(__file__).parent / "fixtures" / "nuc02_audit.txt").read_text(encoding="utf-8")


def test_parse_full_audit() -> None:
    r = parse_audit_output("nuc02", FIXTURE)
    assert r.hostname == "nuc02"
    assert r.architecture == "amd64"
    assert r.cpu_model == "13th Gen Intel(R) Core(TM) i5-1340P"
    assert (r.cores, r.threads, r.max_mhz) == (12, 16, 4600)
    assert r.ram_total_gb == 16
    assert (r.ram_slots_used, r.ram_slots_total) == (1, 2)
    assert r.dimms[0].part_number == "TEAMGROUP-SD4-3200"
    assert [d.name for d in r.disks] == ["nvme0n1"]
    assert r.disks[0].size_gb == 512
    assert r.primary_interface == "enp86s0"
    assert r.lan_ip == "10.0.0.10"
    assert r.mac_ethernet == "48:21:0B:5A:45:33"
    assert r.tailscale_ip == "100.99.32.117"
    assert r.tailscale_fqdn == "nuc02.tail87cf32.ts.net"
    assert r.os_pretty_name == "Debian GNU/Linux 13 (trixie)"
    assert r.kernel == "6.12.94+deb13-amd64"
    assert r.warnings == []


def test_crlf_output_from_windows_ssh() -> None:
    r = parse_audit_output("nuc02", FIXTURE.replace("\n", "\r\n"))
    assert r.kernel == "6.12.94+deb13-amd64"


def test_missing_sudo_falls_back_to_meminfo() -> None:
    sections = split_sections(FIXTURE)
    sections["dmidecode"] = ""
    text = "".join(f"\n@@@{k}\n{v}\n" for k, v in sections.items())
    r = parse_audit_output("nuc02", text)
    assert r.ram_total_gb == 15  # 16064952 kB usable
    assert r.ram_slots_total is None
    assert any("sudo" in w for w in r.warnings)


def test_truncated_output_is_an_error() -> None:
    with pytest.raises(AuditError):
        parse_audit_output("nuc02", FIXTURE.split("@@@end")[0])
