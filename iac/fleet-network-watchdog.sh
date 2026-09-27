#!/usr/bin/env bash
# fleet-network-watchdog.sh
# Automated watchdog for headless fleet nodes (Intel NUCs / RPis).
# - Detects Ethernet PHY lockups or network isolation.
# - Attempts in-kernel PCIe bus reset / driver rebind before power actions.
# - Protects interactive console sessions (tty) from unexpected reboots.
# - Escalates recovery: 1 soft reboot -> 1 clean shutdown (to drain or prevent loop).

set -euo pipefail

STATE_FILE="/var/lib/fleet/net-fail-count"
mkdir -p /var/lib/fleet

# 1. Do nothing if a human is logged in at physical tty console
if who | grep -q 'tty[0-9]'; then
    echo "[watchdog] Physical console session detected. Skipping automated reboot/shutdown."
    exit 0
fi

# 2. Check if abort flag is present
if [ -f "/tmp/cancel-watchdog" ]; then
    echo "[watchdog] /tmp/cancel-watchdog flag found. Aborting watchdog."
    exit 0
fi

# 3. Check network health
# A. Carrier detection on any ethernet interface
has_carrier=false
for carrier_path in /sys/class/net/e*/carrier /sys/class/net/en*/carrier; do
    if [ -f "$carrier_path" ] && [ "$(cat "$carrier_path" 2>/dev/null)" = "1" ]; then
        has_carrier=true
        break
    fi
done

# B. Connectivity test (ping gateway or 1.1.1.1)
can_ping=false
if [ "$has_carrier" = true ]; then
    gateway_ip=$(ip route show default 2>/dev/null | awk '{print $3}' | head -n 1 || true)
    target="${gateway_ip:-1.1.1.1}"
    if ping -c 2 -W 2 "$target" >/dev/null 2>&1; then
        can_ping=true
    fi
fi

# 4. If network is healthy, reset counter and exit
if [ "$can_ping" = true ]; then
    if [ -f "$STATE_FILE" ] && [ "$(cat "$STATE_FILE" 2>/dev/null)" != "0" ]; then
        echo "0" > "$STATE_FILE"
        echo "[watchdog] Network is healthy. Reset failure counter to 0."
    fi
    exit 0
fi

# 5. Network is DOWN: Begin recovery procedure
echo "[watchdog] WARNING: Network is DOWN (carrier=$has_carrier, ping=$can_ping)"

# Recovery Phase 1: In-kernel PCIe reset for Intel I225/I226 (igc)
igc_pci=$(lspci -D 2>/dev/null | grep -i 'Ethernet controller' | grep -i 'Intel' | awk '{print $1}' | head -n 1 || true)
if [ -n "$igc_pci" ] && [ -d "/sys/bus/pci/drivers/igc" ]; then
    echo "[watchdog] Attempting PCIe driver unbind/bind for $igc_pci..."
    echo "$igc_pci" > /sys/bus/pci/drivers/igc/unbind 2>/dev/null || true
    sleep 2
    echo "$igc_pci" > /sys/bus/pci/drivers/igc/bind 2>/dev/null || true
    sleep 3
    # Try DHCP renew
    systemctl restart networking 2>/dev/null || true
    sleep 5

    # Re-check ping
    if ping -c 2 -W 2 "${gateway_ip:-1.1.1.1}" >/dev/null 2>&1; then
        echo "[watchdog] Network recovered via PCIe rebind! Resetting counter."
        echo "0" > "$STATE_FILE"
        exit 0
    fi
fi

# Recovery Phase 2: Counter-based Reboot vs Shutdown Escalation
FAIL_COUNT=0
if [ -f "$STATE_FILE" ]; then
    FAIL_COUNT=$(cat "$STATE_FILE" 2>/dev/null || echo 0)
fi

if [ "$FAIL_COUNT" -eq 0 ]; then
    echo "1" > "$STATE_FILE"
    echo "[watchdog] PCIe reset failed. First offline boot recorded (count=1). Triggering reboot in 15 seconds..."
    wall "[watchdog] No network detected. Rebooting node in 15 seconds..." 2>/dev/null || true
    sleep 15
    systemctl reboot
else
    echo "2" > "$STATE_FILE"
    echo "[watchdog] Node remained offline across reboot (count=$FAIL_COUNT). Powering down cleanly to protect hardware..."
    wall "[watchdog] Network still offline across reboot. Shutting down node in 15 seconds..." 2>/dev/null || true
    sleep 15
    systemctl poweroff
fi
