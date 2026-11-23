# ECHONET Lite 0x03B8 (Combination microwave oven) – as implemented by the Sharp AX‑XA10

Observed 2026‑11‑23 with `just inspect`. Spec names from ECHONET Lite APPENDIX Release R
(as encoded in `pychonet` 2.8.2 `CombinationMicrowaveOven`).

## Node profile (0x0EF001)

| EPC | Value | Meaning |
|---|---|---|
| `8A` | `000005` | Manufacturer: Sharp |
| `8C` | `HW-A04` | Node firmware / module product code |
| `83` | `fe 000005 …` | Identification number (manufacturer code + the module's MAC in EUI‑64 form) |
| `82` | `010a0100` | ECHONET Lite version 1.10 |
| `D6` | `01 03B8 01` | One instance: combination microwave oven |

## Oven object (0x03B801)

Property maps:

| Map | EPCs |
|---|---|
| GET (`9F`) | `80 81 82 85 86 88 89 8A 8B 8C 9D 9E 9F B0 B1 B2 E1 E6 F0 F1 F2` |
| SET (`9E`) | `81` |
| INF announce (`9D`) | `80 81 86 88 89 B0 B1 F2` |

Standard properties:

| EPC | Name | Encoding | Seen |
|---|---|---|---|
| `80` | Operation status | `30` on / `31` off | `31` (standby) |
| `81` | Installation location | | `00` |
| `82` | Standard version | | `00004700` (Release G) |
| `85` | Cumulative power consumption | u32, 0.001 kWh | `0001F5E5` = 128.485 kWh |
| `86` | Manufacturer fault code | | `080000050000…` |
| `88` | Fault status | `41` fault / `42` none | `42` |
| `89` | Fault description | | `0000` |
| `8B` | Business facility code | | `313034` ("104") |
| `8C` | Product code | ASCII | `AX-XA10` |
| `B0` | Door open/close | `41` open / `42` closed | `41` (door was physically open – confirmed) |
| `B1` | Heating status | `40` initial, `41` heating, `42` suspended, `43` cycle complete, `44` setting, `45` preheating, `46` preheat maintenance, `47` manual stop | `40` |
| `B2` | Heating setting | `41` start, `42` suspend, `43` stop | `43` |
| `E1` | Automatic heating setting | `41` auto, `42` manual, `FF` n/a | `42` |
| `E6` | Remaining heating time | `HH MM SS` | `000000` |

Not implemented by this model (absent from GET map): `E0` heating mode, `E2` auto level, `D0` auto menu,
`D1` oven mode, `D5` preheating, `E3` chamber temp, `E4` food temp, `E5` heating time, `E7` microwave power.

## Sharp vendor properties (undecoded)

| EPC | Len | Observed (idle, door open) | Notes |
|---|---|---|---|
| `F0` | 32 | `51 40 00 00 04 00 1e 0f 87 4b 3c 28 51 01 00 05 0d 3e 1f 04 3f 00 00 00 00 00 00 00 00 06 03 01` | Likely last/current cook settings (menu, temp, time). `1e 0f 87 4b 3c 28` = 30 15 135 75 60 40 look like temperatures / minutes. |
| `F1` | 32 | `0001A019 00026F39 0002FB8B 0000F70F 0000C31C 00000000 00000000 00000000` | Five u32 counters: 106521 / 159545 / 195467 / 63247 / 49948 – probably seconds (or counts) per heating mode. |
| `F2` | 16 | `03 00 40 ff 00 00 00 00 31 01 4d 00 41 41 00 00` | Announced on change (in INF map) → live status bundle. Bytes 8/12/13 (`31`,`41`,`41`) mirror op‑status / door / something. `4d` = 77 unknown. |

To decode, run `just monitor` during a cook cycle and diff the CSV rows.
