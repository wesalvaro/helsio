#!/usr/bin/env python3
"""Deploy the Healsio integration to Home Assistant (idempotent).

  deploy.py integration   HACS: enable -> download ECHONET Lite -> restart HA -> add device -> restore HACS state
  deploy.py helpers       create the template helpers defined in homeassistant/packages/helsio.yaml
  deploy.py helpers-rm    delete those helpers (so `helpers` re-creates them after a YAML change)
  deploy.py verify        render every template server-side and list the resulting entities
  deploy.py all           integration + helpers + verify

Needs PyYAML (see Justfile `venv`). Token/URL handling as in ha_api.py; oven host from
$HELSIO_HOST or multicast discovery (tools/echonet.py).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
import ha_api  # noqa: E402
from echonet import oven_host  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "homeassistant" / "packages" / "helsio.yaml"

HACS_REPO = "scottyphillips/echonetlite_homeassistant"
OVEN_TITLE = "Helsio"


def entries(domain: str) -> list[dict]:
    return [e for e in ha_api.rest("GET", "/api/config/config_entries/entry") if e["domain"] == domain]


def log(msg: str) -> None:
    print(f"==> {msg}", flush=True)


# ------------------------------------------------------------------ integration
def deploy_integration() -> None:
    hacs = entries("hacs")
    if not hacs:
        raise SystemExit("HACS is not installed in this Home Assistant; install it first.")
    hacs = hacs[0]
    was_disabled = hacs.get("disabled_by") is not None
    ws = ha_api.WS()

    if was_disabled:
        log("enabling HACS (temporarily)")
        ws.call("config_entries/disable", entry_id=hacs["entry_id"], disabled_by=None)
        for _ in range(30):
            time.sleep(2)
            try:
                ha_api.WS().call("hacs/info")
                break
            except Exception:
                pass
        else:
            raise SystemExit("HACS did not come up")

    try:
        repos = ha_api.WS().call("hacs/repositories/list", categories=["integration"])
        repo = next(r for r in repos if r["full_name"] == HACS_REPO)
        if repo.get("installed"):
            log(f"{HACS_REPO} already installed ({repo.get('installed_version')})")
            restarted = False
        else:
            log(f"downloading {HACS_REPO} {repo.get('available_version')}")
            ha_api.WS().call("hacs/repository/download", repository=repo["id"])
            log("restarting Home Assistant")
            ha_api.cmd_restart()
            restarted = True
    finally:
        if was_disabled:
            log("disabling HACS again")
            ha_api.WS().call("config_entries/disable", entry_id=hacs["entry_id"], disabled_by="user")

    if entries("echonetlite"):
        log("echonetlite config entry already exists")
    else:
        if not restarted:
            log("echonetlite integration present but not loaded; restarting Home Assistant")
            ha_api.cmd_restart()
        host = oven_host()
        log(f"adding ECHONET Lite device {host} as '{OVEN_TITLE}'")
        ha_api.cmd_flow("echonetlite", [f"host={host}", f"title={OVEN_TITLE}"])


# ---------------------------------------------------------------------- helpers
def helper_specs() -> list[tuple[str, dict, str | None]]:
    pkg = yaml.safe_load(PACKAGE.read_text())
    specs = []
    for block in pkg.get("template", []):
        for ent in block.get("sensor", []):
            d = {"name": ent["name"], "state": ent["state"].strip()}
            for k in ("unit_of_measurement", "device_class", "state_class"):
                if k in ent:
                    d[k] = ent[k]
            specs.append(("sensor", d, ent.get("icon")))
        for ent in block.get("binary_sensor", []):
            d = {"name": ent["name"], "state": ent["state"].strip()}
            if "device_class" in ent:
                d["device_class"] = ent["device_class"]
            specs.append(("binary_sensor", d, ent.get("icon")))
    return specs


def oven_device_id() -> str | None:
    enl = entries("echonetlite")
    if not enl:
        return None
    eid = enl[0]["entry_id"]
    for d in ha_api.WS().call("config/device_registry/list"):
        if eid in d.get("config_entries", []):
            return d["id"]
    return None


def deploy_helpers() -> None:
    device = oven_device_id()
    existing = {e["title"] for e in entries("template")}
    ws = ha_api.WS()
    for kind, data, icon in helper_specs():
        if data["name"] in existing:
            log(f"helper exists: {data['name']}")
            continue
        if device:
            data["device_id"] = device
        f = ha_api.rest("POST", "/api/config/config_entries/flow", {"handler": "template", "show_advanced_options": True})
        ha_api.rest("POST", f"/api/config/config_entries/flow/{f['flow_id']}", {"next_step_id": kind})
        r = ha_api.rest("POST", f"/api/config/config_entries/flow/{f['flow_id']}", data)
        if r.get("type") != "create_entry":
            raise SystemExit(f"creating {data['name']} failed: {r}")
        log(f"created {kind} '{data['name']}'")
        if icon and isinstance(icon, str) and icon.startswith("mdi:"):
            time.sleep(1)
            slug = data["name"].lower().replace(" ", "_")
            try:
                ws.call("config/entity_registry/update", entity_id=f"{kind}.{slug}", icon=icon)
            except Exception as e:  # entity id may differ if it already existed
                print(f"    (icon not set: {e})")


def remove_helpers() -> None:
    names = {d["name"] for _, d, _ in helper_specs()}
    for e in entries("template"):
        if e["title"] in names:
            ha_api.rest("DELETE", f"/api/config/config_entries/entry/{e['entry_id']}")
            log(f"deleted helper '{e['title']}'")


# ----------------------------------------------------------------------- verify
def verify() -> None:
    ok = True
    for kind, data, _ in helper_specs():
        try:
            out = ha_api.render(data["state"]).strip()
        except Exception as e:
            out, ok = f"ERROR {e}", False
        print(f"{kind}.{data['name']:<24} renders -> {out!r}")
    print()
    ha_api.cmd_states("helsio")
    if not ok:
        raise SystemExit(1)


def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else "help"
    if cmd == "integration":
        deploy_integration()
    elif cmd == "helpers":
        deploy_helpers()
    elif cmd == "helpers-rm":
        remove_helpers()
    elif cmd == "verify":
        verify()
    elif cmd == "all":
        deploy_integration()
        deploy_helpers()
        verify()
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
