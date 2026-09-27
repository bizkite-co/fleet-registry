# Fleet Registry & Node Management

Central inventory, automated provisioning engine, and operational runbooks for the **InTEGr8or Homelab Fleet** (Intel NUCs, Raspberry Pis, and edge nodes).

---

## 1. Fleet Overview

| Node ID | Hostname | Model / Hardware | CPU Cores / Threads | RAM | Storage | Tailscale IP | Status | Primary Role |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`nuc01`** | `NUC01` | Intel NUC 11 Performance (NUC11PAHi5) | 4c / 8t @ 4.2 GHz | 8 GB DDR4 (1x 8GB) | 250 GB WD Black SN770 | `100.88.63.109` | **Online** | Primary Dev Box |
| **`nuc02`** | `NUC02` | Intel NUC 13 Pro Slim (NUC13ANKi5000) | 12c / 16t @ 4.6 GHz | 16 GB DDR4 (1x 16GB) | 512 GB TEAM NVMe | `100.99.32.117` | **Online** | High-Compute / Worker |
| **`nuc03..08`**| *Pending* | Intel NUCs (NUC10/11/13 mix) | TBD | TBD | TBD | Pending | Unboxed | Cluster Nodes |
| **`pi-nodes`** | *Pending* | Raspberry Pi 5 / 4 | 4c / 4t (ARM64) | 4GB / 8GB | NVMe / MicroSD | Pending | Online | IoT / Edge |

*Detailed machine-readable specifications are tracked in [`inventory/devices.json`](./inventory/devices.json).*

---

## 2. Repository Structure

```text
fleet-registry/
├── inventory/
│   ├── devices.json              # Source of truth: hardware specs, MACs, IPs, and roles
│   └── schema.json               # JSON Schema for devices.json (`fr schema --write`)
├── src/fleet_registry/
│   ├── core/                     # Business logic: models, inventory I/O, SSH, audit, reconcile
│   ├── cli.py                    # `fr` command line (Typer + Rich)
│   ├── tui/                      # `fr` dashboard (Textual)
│   └── render.py                 # Rich tables shared by CLI and TUI (verkit theme)
├── tests/
├── usb/
│   ├── preseed.cfg               # Master Debian unattended installer configuration
│   └── grub-menu.cfg             # Fast boot entry configuration for USB installer
└── docs/
    ├── battery-backup-guide.md   # 19V Mini DC-to-DC UPS and USB-PD trigger guide
    └── 1password-headless-guide.md # Zero-secrets Windows Hello biometrics over SSH
```

---

## 3. The `fr` CLI / TUI

`fleet-registry` is a cross-platform Python tool (Windows, WSL, Linux, macOS). `fr` is the
short alias for `fleet-registry`.

### Install

Anywhere (from PyPI):
```bash
uv tool install fleet-registry
uv tool upgrade fleet-registry      # later
```

In this checkout, [mise](https://mise.jdx.dev) activates a per-OS venv (`.venv-windows` /
`.venv-linux`) holding an **editable** install, so `fr` here always runs the working-tree code:
```bash
mise trust && mise install && mise run setup   # once (re-run setup when deps change)
```

### Usage

| Command | What it does |
| :--- | :--- |
| `fr` | Open the TUI dashboard (`a` audit, `A` audit all, `u` apply audit, `p` ping, `r` reload, `q` quit; vim nav: `j`/`k` down/up, `h`/`l` table/detail pane, `g`/`G` top/bottom, `ctrl+d`/`ctrl+u` page) |
| `fr list [--ping]` | Fleet table, optionally with SSH reachability |
| `fr show nuc02` | One device's inventory record |
| `fr audit nuc02` | Audit hardware/network/OS over SSH and diff against the inventory |
| `fr audit --all --update` | Audit every addressable node and write measured changes |
| `fr audit nuc03 --update --add` | Register a freshly installed node |
| `fr audit nuc02 --json` | Raw audit data |
| `fr config [--inventory PATH] [--ssh CLIENT]` | Show / set user settings |
| `fr schema --write` | Regenerate `inventory/schema.json` |
| `fr version` | Installed vs. latest PyPI version |

Audits only update measurable fields (CPU, cores/threads, RAM, slots, MAC, IPs, Tailscale,
OS, kernel); hand-written descriptions like `model`, `storage`, and `role` are never touched.
RAM slot details need passwordless `sudo` for `dmidecode` on the node.

**Finding the inventory:** `--inventory` → `$FLEET_REGISTRY_INVENTORY` → `inventory/devices.json`
in the current directory or a parent → `fr config --inventory PATH`. To use `fr` outside the
checkout, run once: `fr config --inventory ~/repos/fleet-registry/inventory/devices.json`.

**SSH client:** `fr` shells out to OpenSSH so `~/.ssh/config` host aliases apply. On Windows
*and in WSL* it uses the Windows OpenSSH client (`C:\Windows\System32\OpenSSH\ssh.exe`), so
the 1Password / Windows Hello agent works with no socket bridge. Override with `$FLEET_SSH` or
`fr config --ssh ssh`.

### Development & releases

```bash
mise run test        # pytest
mise run lint        # ruff + mypy
mise run release     # verkit: bump patch, tag vX.Y.Z, push → GitHub Actions publishes to PyPI
mise run release minor
```

Rich output uses the shared [verkit](https://github.com/bizkite-co/verkit) theme.

---

## 4. Quick Start: Provisioning a New NUC

### Step 1: Automated Debian Install via USB
1. Plug the Debian Installer USB into the new NUC and connect an Ethernet cable.
2. Power on and tap `F10` for the boot menu. Select the USB drive.
3. Select **`Automated Headless Install (Preseed)`**.
4. The installer prompts once for a **hostname** (e.g. `nuc03`), then automatically wipes the NVMe drive, installs Debian headless, sets up user `mstouffer`, pre-injects your SSH keys, enables passwordless `sudo`, and reboots.

### Step 2: Connect via SSH
From Windows or WSL:
```bash
ssh mstouffer@<hostname>.local
# or using the host alias:
ssh nuc02
```

### Step 3: Hardware Audit & Inventory Registration
```bash
fr audit nuc03 --update --add
```

---

## 5. Documentation & Operational Runbooks

* [1Password + Windows Hello Over SSH Runbook](./docs/1password-headless-guide.md)
* [Power & Battery Backup Guide (Mini DC UPS)](./docs/battery-backup-guide.md)
