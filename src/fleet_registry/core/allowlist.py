"""Generate Antigravity CLI execution allowlist rules from fleet inventory and Tailscale."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from fleet_registry.core.models import Inventory

SETTINGS_PATH_WIN = Path(os.path.expanduser(r"~/.gemini/antigravity-cli/settings.json"))


def get_fleet_hosts(inventory: Inventory) -> list[str]:
    hosts = set()
    for d in inventory.devices:
        if d.id:
            hosts.add(d.id.lower())
        if d.hostname:
            hosts.add(d.hostname.lower())
        if d.network.tailscale_ip:
            hosts.add(d.network.tailscale_ip)
        if d.network.lan_ip:
            hosts.add(d.network.lan_ip)
    return sorted(hosts)


def generate_baked_rules(hosts: list[str]) -> list[dict[str, str]]:
    hosts_pattern = "|".join(re.escape(h) for h in hosts)
    git_subcmds = (
        "add|status|diff|log|show|branch|tag|remote|rev-parse|ls-files|"
        "ls-remote|blame|describe|shortlog|cat-file|merge-base|annex"
    )
    return [
        {
            "category": "Fleet SSH Target Nodes",
            "rule": f"regex:(?s)command\\((wsl(\\.exe)?\\s+.*)?ssh\\s+.*({hosts_pattern})\\b.*\\)",
        },
        {
            "category": "Fleet SSH Fallback",
            "rule": f"regex:(?s).*ssh\\s+.*({hosts_pattern}).*",
        },
        {
            "category": "Git Safe Operations & Staging",
            "rule": (
                r"regex:(?s)command\((wsl(\.exe)?\s+.*)?git(\s+--no-pager)?(\s+-C\s+\S+)?\s+"
                f"({git_subcmds}).*\\)"
            ),
        },
        {
            "category": "System Inspection Cmdlets",
            "rule": (
                r"regex:(?s)command\((Get-ChildItem|Get-Item|Select-String|Test-Path|"
                r"cat|head|tail|grep|tasklist|ls)\b.*\)"
            ),
        },
        {
            "category": "Development Toolchains",
            "rule": (
                r"regex:(?s)command\((go\s+(build|test|run|version)|"
                r"cargo\s+(check|test|build)|uv\s+(run|tool|sync)|python3?\s+).*\)"
            ),
        },
        {
            "category": "Project Tools & Binaries",
            "rule": r"regex:(?s)command\((\.\\windows-tts\.exe|sharex|ahk|fr|fleet-registry)\b.*\)",
        },
    ]


def apply_allowlist(rules: list[str], target_path: Path | None = None) -> Path:
    path = target_path or SETTINGS_PATH_WIN
    if not path.exists():
        data: dict[str, Any] = {"permissions": {"allow": []}}
    else:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

    existing = data.setdefault("permissions", {}).setdefault("allow", [])
    for r in rules:
        if r not in existing:
            existing.append(r)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return path
