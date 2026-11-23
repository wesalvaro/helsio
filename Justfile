# Sharp Healsio AX-XA10 <-> Home Assistant (local ECHONET Lite)

set shell := ["bash", "-euo", "pipefail", "-c"]
set dotenv-load

venv := ".venv"
py   := venv + "/bin/python"

# List all available recipes
default:
    @just --list

# Create the local Python venv (PyYAML only; everything else is stdlib)
venv:
    test -x {{py}} || (python3 -m venv {{venv}} && {{py}} -m pip -q install pyyaml)

# Full deployment: ECHONET Lite integration via HACS, template helpers, verification
deploy: venv
    {{py}} tools/deploy.py all

# HACS (temporarily enabled) -> download ECHONET Lite -> restart HA -> add the oven ($HELSIO_HOST or auto-discovered)
deploy-integration: venv
    {{py}} tools/deploy.py integration

# Create the template helpers from homeassistant/packages/helsio.yaml (idempotent by name)
deploy-helpers: venv
    {{py}} tools/deploy.py helpers

# Delete the template helpers, then re-create them (after editing helsio.yaml)
redeploy-helpers: venv
    {{py}} tools/deploy.py helpers-rm
    {{py}} tools/deploy.py helpers

# Render every template server-side and list all Helsio entities
verify: venv
    {{py}} tools/deploy.py verify

# Show current Helsio entity states in Home Assistant
status:
    python3 tools/ha_api.py states helsio

# Print Helsio entity state changes live (1 s polling, default 5 min)
watch SECONDS="300":
    python3 tools/ha_api.py watch helsio {{SECONDS}}

# Multicast discovery: which LAN hosts answer ECHONET Lite
probe:
    python3 tools/echonet_probe.py

# Dump the oven's node profile, property maps and every readable EPC
inspect HOST="":
    python3 tools/echonet_inspect.py {{HOST}}

# Log oven state (poll + push) to CSV during a cook cycle, for decoding Sharp vendor props
monitor OUT="cook.csv":
    python3 tools/helsio_monitor.py --out {{OUT}}

# Enable or disable HACS ("on" / "off")
hacs STATE:
    python3 tools/ha_api.py entry-disable "$(python3 tools/ha_api.py entries hacs | awk '{print $1}')" {{STATE}}
