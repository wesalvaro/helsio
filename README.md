# Sharp Healsio AX‑XA10 ↔ Home Assistant

Local‑only integration of a Sharp **Healsio AX‑XA10** water oven (ヘルシオ, 2020 model) with Home Assistant.
No COCORO cloud, no app keys, no reverse engineering: the oven speaks **ECHONET Lite** (UDP 3610) on the LAN.
Other Wi‑Fi Healsio / Hotcook models very likely expose the same ECHONET object – run `just probe` to find out.

## What the oven exposes

| | |
|---|---|
| Host | found by multicast discovery, or pinned with `HELSIO_HOST` in `.env` (give the oven a DHCP reservation) |
| ECHONET object | `0x03B8` Combination microwave oven, instance 1 |
| Node | manufacturer `0x000005` (Sharp), firmware `HW-A04`, product `AX-XA10` |
| Readable EPCs | `80 81 82 85 86 88 89 8A 8B 8C 9D 9E 9F B0 B1 B2 E1 E6 F0 F1 F2` |
| Writable EPCs | `81` only → **read‑only device**, no remote start |
| Push (INF) EPCs | `80 81 86 88 89 B0 B1 F2` → door / heating changes arrive instantly |

See [docs/echonet_0x03B8.md](docs/echonet_0x03B8.md) for the property reference and observed values.

## Home Assistant setup

1. **HACS → ECHONET Lite** (`scottyphillips/echonetlite_homeassistant` 4.0.9, `pychonet` 2.8.2), device added by IP, title `Helsio` (`just deploy-integration`). Provides:

   | Entity | Values |
   |---|---|
   | `sensor.helsio_heating_status` | `initial` `heating` `suspended` `cycle-complete` `setting` `preheating` `preheat-maintenance` `manual-stop` |
   | `sensor.helsio_door_open_close_status` | `open` / `closed` |
   | `sensor.helsio_remaining_heating_time_setting` | `HH:MM:SS` |
   | `sensor.helsio_heating_setting` | `start` / `suspend` / `stop` |
   | `sensor.helsio_automatic_heating_setting` | `automatic` / `manual` |
   | `sensor.helsio_measured_cumulative_power_consumption` | kWh, `total_increasing` (Energy dashboard ready) |
   | `binary_sensor.helsio_operation_status`, `binary_sensor.helsio_fault_status` | |

2. **Template helpers** (`just deploy-helpers`; attached to the Helsio device). The YAML equivalent lives in
   [homeassistant/packages/helsio.yaml](homeassistant/packages/helsio.yaml) for reference / re‑creation:

   | Entity | Meaning |
   |---|---|
   | `sensor.helsio_state` | `idle` `cooking` `paused` `done` `setting` `preheating` `preheated` `waiting` |
   | `sensor.helsio_remaining_time` | minutes (float) |
   | `binary_sensor.helsio_door` | `device_class: door` |
   | `binary_sensor.helsio_cooking` | `device_class: running` |

3. **Notifications** – not yet configured. Two ready‑made automations are in the package file (commented out); fill in `NOTIFY_TARGET`.

## Usage (`just`)

Everything goes through the [Justfile](Justfile); run `just` for the list.

| Recipe | What it does |
|---|---|
| `just deploy` | full deployment: integration + helpers + verify |
| `just deploy-integration` | HACS (temporarily enabled) → download ECHONET Lite → restart HA if needed → add the oven (`HELSIO_HOST` or auto‑discovered) → restore HACS state |
| `just deploy-helpers` / `just redeploy-helpers` | create (or delete + recreate) the template helpers from `homeassistant/packages/helsio.yaml` |
| `just verify` | render every template server‑side and list the Helsio entities |
| `just status` / `just watch [SECONDS]` | current entity states / live change log |
| `just probe` / `just inspect [HOST]` | ECHONET Lite discovery / full property dump of the oven |
| `just monitor [OUT]` | log oven state to CSV during a cook (for decoding Sharp's vendor props) |
| `just hacs on\|off` | toggle HACS |

Recipes are idempotent. Setup:

1. Create a long‑lived access token in Home Assistant (profile → Security) and save it to `~/.config/helsio/ha_token`.
2. Optionally `cp .env.example .env` to pin `HELSIO_HOST` / `HA_URL` (defaults: multicast discovery / `http://homeassistant.local:8123`).
3. HACS must be installed (it may be disabled; recipes enable it temporarily and restore its state).

The only Python dependency is PyYAML in a local `.venv` (`just venv`).

Implementation lives in `tools/` (`deploy.py` → `ha_api.py`, plus the three ECHONET scripts); you shouldn't need to call them directly.

## Notes / caveats

- ECHONET Lite discovery and push (INF) updates use multicast (`224.0.23.0:3610`), which does not cross VLANs/subnets on its own. Keep the oven on the same network segment as Home Assistant (and the machine running these tools), or you will only get polled updates — or none, if `UDP/3610` is firewalled.
- Give the oven a DHCP reservation; if you change its IP it holds a 24 h lease, so kick it off Wi‑Fi from your router or power‑cycle it to re‑lease.
- Sharp vendor properties `F0/F1/F2` are not decoded (not exposed by the integration). See the docs file for what is known.
