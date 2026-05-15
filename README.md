# X-PoE — Home Assistant integration

Local control of Amatis X-PoE lighting switches (XS-108H family) over their REST API. No cloud, no relay — talks directly to the switch on your LAN.

## Features

- 8 dimmable lights per switch (one per physical port). On/off + brightness 0–100%.
- Per-port power sensors (W).
- Device voltage and total power sensors.
- Auto-discovery of switches via mDNS (`_xpoe_lighting._tcp.local.`), with active fallback scan when adding manually.
- Multi-switch support — add as many as you have.
- DHCP-resilient: switches re-discovered by MAC, IP updates automatically.

## Installation

### HACS (recommended)

1. In HACS, go to **Integrations** → ⋮ → **Custom repositories**.
2. Paste the repository URL and pick category **Integration**.
3. Click **Install** on the X-PoE entry, then restart Home Assistant.
4. Go to **Settings → Devices & Services → Add Integration** → search "X-PoE".

### Manual

1. Copy the `custom_components/xpoe/` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.
3. **Settings → Devices & Services → Add Integration** → "X-PoE".

## Adding a switch

When you launch the flow it does a quick mDNS scan:

- **Switches found** → pick one from the list, enter username + password (defaults `xpoeclient` / `xpoepass`).
- **Nothing found** → enter the IP manually. The form will say "0 X-PoE switches found on the network".

Already-configured switches don't appear in the picker.

## Entities created (per switch)

| Type | Count | What |
|---|---:|---|
| Light | 8 | Port 1 – Port 8, brightness control |
| Sensor | 8 | Port N power (W) |
| Sensor | 2 | Device voltage (V), total power (W) |

## Troubleshooting

**No switches found in the picker** — confirm the switch and Home Assistant are on the same broadcast domain (same VLAN/subnet, no mDNS proxy in between). If Home Assistant runs in a container, make sure it sees multicast (host networking on Docker).

**`Cannot reach the switch`** — verify HTTPS is reachable on port 443 of the switch's IP. The integration tolerates self-signed certs by default.

**`Login failed`** — credentials wrong. The switch's defaults are `xpoeclient` / `xpoepass` unless changed.


## Status

Phase 1 — brightness/power/voltage. Future: color temp + RGB via `/api/port_color_temp` (out of scope for now).