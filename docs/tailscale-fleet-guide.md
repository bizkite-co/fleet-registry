# Tailscale Fleet Configuration & Tailnet Integration Guide

This guide details how Tailscale networking is configured and integrated across the **InTEGr8or Homelab Fleet** (Intel NUCs, Raspberry Pis, and workstations) and how it powers discovery and agent automation in `fleet-registry`.

---

## 1. Tailnet Architecture Overview

The fleet operates on a private Tailscale network (tailnet) providing encrypted WireGuard mesh connectivity across physical nodes, WSL environments, and remote developer machines:

* **Subnet**: Tailscale CGNAT IP range (`100.64.0.0/10`).
* **MagicDNS**: Automatically provides short names (`nuc01`, `nuc02`) and fully-qualified domain names (`nuc01.tail87cf32.ts.net`).
* **Machine Inventory Mapping**:
  * `nuc01` &rarr; `100.88.63.109` (`nuc01.tail87cf32.ts.net`)
  * `nuc02` &rarr; `100.99.32.117` (`nuc02.tail87cf32.ts.net`)
  * Windows Workstation (`DESKTOP-NU23FHO`) &rarr; Shared tailnet gateway.

---

## 2. Discovery Engine (`fleet_registry.core.tailscale`)

`fleet-registry` includes native discovery of online and offline tailnet nodes via `fr discover`:

```bash
# Compare Tailscale tailnet nodes against inventory/devices.json:
fr discover

# Include offline and mobile devices:
fr discover --all

# Audit and register all new Linux nodes found on the tailnet:
fr discover --add
```

### How Client Discovery Works
* On **Windows**: Looks for `tailscale` on `PATH` or `C:\Program Files\Tailscale\tailscale.exe`.
* In **WSL**: WSL typically shares the host network without running its own `tailscaled` daemon. The engine detects WSL and transparently queries the Windows client (`/mnt/c/Program Files/Tailscale/tailscale.exe` or `tailscale.exe`).
* Custom binary override: Set the `FLEET_TAILSCALE` environment variable.

---

## 3. Recommended Tailnet ACL Policy

To allow developer machines and AI coding agents to manage fleet nodes while enforcing least-privilege, configure the tailnet ACL policy as follows:

```jsonc
{
  "acls": [
    // Allow dev workstations full SSH and management access to all homelab nodes
    {
      "action": "accept",
      "src": ["tag:dev-workstations", "autogroup:admin"],
      "dst": ["tag:fleet-node:*"]
    },
    // Allow fleet cluster nodes to communicate with each other
    {
      "action": "accept",
      "src": ["tag:fleet-node"],
      "dst": ["tag:fleet-node:*"]
    }
  ],
  "tagOwners": {
    "tag:fleet-node": ["autogroup:admin"],
    "tag:dev-workstations": ["autogroup:admin"]
  },
  "ssh": [
    {
      "action": "accept",
      "src": ["tag:dev-workstations", "autogroup:admin"],
      "dst": ["tag:fleet-node"],
      "users": ["mstouffer", "root"]
    }
  ]
}
```

---

## 4. Antigravity Agent Auto-Approval Integration

Because fleet nodes have fixed Tailscale IPs and MagicDNS short names, coding agents (Antigravity CLI, Claude Code, etc.) can be granted pre-approval to orchestrate tasks across the tailnet without manual prompt fatigue:

* **Host Patterns**: Matches direct hostname (`nuc01`, `nuc02`), user prefixes (`mstouffer@nuc01`), and Tailscale IPs (`100.88.63.109`, `100.99.32.117`).
* **Allow Rule**:
  ```json
  "regex:(?s)command\\((wsl(\\.exe)?\\s+.*)?ssh\\s+.*(100\\.88\\.63\\.109|100\\.99\\.32\\.117|nuc01|nuc02)\\b.*\\)"
  ```
* **Management**: Use `python scripts/hoover_allowlist.py --apply` to automatically bake all discovered tailnet and inventory nodes into your local agent allowlist.
