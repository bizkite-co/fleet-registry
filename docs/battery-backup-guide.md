# Intel NUC 11 (NUC11PAH) Power & Battery Backup Guide

This guide covers options for keeping the Intel NUC 11 running through short power blips and extended outages without the bulk and energy waste of a traditional 120V AC-to-DC-to-AC-to-DC uninterruptible power supply (UPS).

---

## 1. Hardware Power Specifications

* **Power Connector:** Rear DC Barrel Jack (**5.5mm OD × 2.5mm ID**, Center-Positive).
* **Input Voltage:** **19V DC** (Safe tolerance: ~17.5V to 21.0V).
* **Power Draw:**
  * **Idle:** ~8W – 12W (typical headless Debian running background services).
  * **Moderate Load:** ~20W – 35W (compilation, database queries, light containers).
  * **Peak Turbo Burst:** ~50W – 65W (sustained heavy multi-core compilation).
* **Onboard USB-C Ports:**
  * The front and rear Thunderbolt 3 / USB4 Type-C ports are **Power Source / Output only** (5V/9V up to 15W).
  * The NUC **cannot be charged or powered directly through its USB-C ports**. All power must enter through the 19V rear barrel jack.

---

## 2. Option A: USB-C Power Delivery (PD) to 19V/20V DC Cable

You can run the NUC from modern USB-C PD power banks or GaN wall chargers using a specialized trigger cable.

### How It Works
* Use a **"USB-C to 20V DC 5.5mm × 2.5mm PD Trigger Cable"** (or adapter dongle).
* Inside the cable's USB-C plug is a hardware PD sink chip (e.g., IP2721 / CH224K) that negotiates the **20V profile** from any standard USB-PD charger or battery bank.
* The 20V output is within the NUC's 19V ± 10% operational range and works safely.

### Requirements for the Power Source:
1. Must support **USB-PD 3.0 at 20V**.
2. Must output at least **65W (20V @ 3.25A)**, though **100W (20V @ 5A)** is strongly recommended to handle peak CPU turbo spikes without voltage sagging.

### ⚠️ The Gotcha: Power Banks as a UPS
Most standard consumer USB-C power banks with "pass-through charging" are **unsuitable as a 24/7 UPS**:
* When wall power drops, standard power banks take **100ms – 500ms** to switch from charging circuit to battery output.
* That momentary power drop causes the NUC to hard-reboot.
* *Exception:* Power banks explicitly engineered with **0ms Uninterruptible Pass-Through / EPS mode** (such as specialized industrial power banks or high-end models like the Zendure SuperTank or Shargeek with UPS modes).

---

## 3. Option B: Native "Mini DC-to-DC UPS" (Recommended)

Instead of converting `120V AC → 12V DC (battery) → 120V AC (inverter) → 19V DC (NUC brick)`, a native Mini DC UPS operates entirely in DC:

```text
Wall Outlet (120V AC)
       │
       ▼
19V DC Power Supply
       │
       ▼
[ Mini DC UPS (18650 Li-ion Battery Buffer) ]
       │  (True 0ms switchover, zero inverter loss)
       ▼
19V DC Barrel Cable (5.5 × 2.5mm)
       │
       ▼
Intel NUC 11 (NUC11PAH)
```

### Why This Is the Superior Setup:
1. **0ms Switchover Time:** The lithium battery cells sit in parallel with the DC bus. When wall power fails, the battery is already connected. Voltage drop is **0ms**.
2. **High Efficiency & Silent:** No DC-to-AC inverters, no cooling fans, no transformer hum.
3. **Massive Runtime for Size:** Because no power is wasted on an inverter, a compact ~40Wh–70Wh battery pack will run an 8W–12W idling NUC for **3 to 6 hours**.
4. **Protects SSD & Filesystems:** Eliminates dirty power cycles and prevents NVMe filesystem corruption on Debian.

### Recommended Models & Search Terms:
* **TalentCell Multi-Voltage 12V/19V/24V UPS Lithium Battery:**
  * Model: **TalentCell NB7102** or **YB1208300** (~$45 – $65 on Amazon).
  * Features a physical voltage selector switch (set to **19V**), includes the 5.5×2.5mm barrel cables, and supports simultaneous charging and discharging.
* **Shanqiu / SKE 19V Mini DC UPS:**
  * Designed specifically for mini-PCs, POE switches, and routers (~$40 – $55).
* **Keywords to search:** `"19V Mini DC UPS"`, `"19V battery backup for mini PC"`, `"19V router UPS"`.

---

## 4. Quick Comparison

| Solution | Switchover Latency | Efficiency | Size / Noise | Estimated Cost | Best For |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Traditional AC UPS** | 4ms – 10ms | Poor (65–75%) | Bulky, hum/fan | $60 – $90 | Whole desks (monitors + PC) |
| **Standard USB-PD Bank** | 100ms – 500ms | High (90%+) | Tiny, silent | $40 – $80 + $10 cable | Portable/Field use (NOT 24/7 UPS) |
| **Mini DC-to-DC UPS** | **0ms (Instant)** | **Excellent (95%+)** | **Compact, silent** | **$45 – $65** | **Headless NUC 24/7 Protection** |

---

## 5. Summary Checklist Before Buying

* [ ] Verify connector size: **5.5mm outer diameter × 2.5mm inner diameter** (barrel connector).
* [ ] Verify voltage output: **19V DC** (or 20V if using a certified USB-PD 65W/100W trigger cable).
* [ ] Verify switchover spec: **0ms / Uninterruptible Buffer** (essential so the NUC doesn't reset during a flicker).
