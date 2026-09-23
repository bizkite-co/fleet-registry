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
│   └── devices.json              # Source of truth: Hardware specs, MACs, IPs, and roles
├── scripts/
│   ├── Audit-FleetNode.ps1       # Audits remote node hardware over SSH
│   └── Provision-FleetNode.ps1   # Pushes dotfiles, Mise tools, and Tailscale
├── usb/
│   ├── preseed.cfg               # Master Debian unattended installer configuration
│   └── grub-menu.cfg             # Fast boot entry configuration for USB installer
└── docs/
    ├── battery-backup-guide.md   # 19V Mini DC-to-DC UPS and USB-PD trigger guide
    ├── 1password-headless-guide.md# Zero-secrets Windows Hello biometrics over SSH
    └── nuc-hardware-specs.md     # Comparison of NUC11 vs NUC13 architectures
```

---

## 3. Quick Start: Provisioning a New NUC

### Step 1: Automated Debian Install via USB
1. Plug the Debian Installer USB into the new NUC and connect an Ethernet cable.
2. Power on and tap `F10` for the boot menu. Select the USB drive.
3. Select **`Automated Headless Install (Preseed)`**.
4. The installer prompts once for a **hostname** (e.g. `nuc03`), then automatically wipes the NVMe drive, installs Debian headless, sets up user `mstouffer`, pre-injects your SSH keys, enables passwordless `sudo`, and reboots.

### Step 2: Connect via SSH
From your Windows laptop or WSL:
```powershell
ssh mstouffer@<hostname>.local
# or using the host alias:
ssh nuc02
```

### Step 3: Hardware Audit & Inventory Registration
Run the audit script to fetch specs:
```powershell
.\scripts\Audit-FleetNode.ps1 -NodeName nuc02
```

---

## 4. Documentation & Operational Runbooks

* [1Password + Windows Hello Over SSH Runbook](./docs/1password-headless-guide.md)
* [Power & Battery Backup Guide (Mini DC UPS)](./docs/battery-backup-guide.md)
