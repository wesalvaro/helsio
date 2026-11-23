#!/usr/bin/env python3
"""Minimal Home Assistant REST + WebSocket helper (stdlib only).

Token is read from $HA_TOKEN or ~/.config/helsio/ha_token; URL from $HA_URL
(default http://homeassistant.local:8123).

Subcommands:
  states [REGEX]                 list entity states (optionally filtered)
  watch [REGEX] [SECONDS]        print state changes of matching entities (1 s polling)
  entries [DOMAIN]               list config entries
  entry-disable ENTRY_ID on|off  disable / re-enable a config entry
  hacs-list REGEX                search HACS integration repositories
  hacs-download REPO_ID          download a HACS repository
  restart                        restart HA and wait until it is back
  flow HANDLER key=value ...     start a config flow and submit one user step
  ws TYPE [JSON]                 raw websocket command
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import socket
import ssl
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

HA_URL = os.environ.get("HA_URL", "http://homeassistant.local:8123").rstrip("/")


def token() -> str:
    tok = os.environ.get("HA_TOKEN")
    if not tok:
        tok = Path("~/.config/helsio/ha_token").expanduser().read_text().strip()
    return tok


# --------------------------------------------------------------------------- REST
def rest(method: str, path: str, body: Any | None = None, timeout: float = 30) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{HA_URL}{path}",
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        ctype = resp.headers.get("Content-Type", "")
    if not raw:
        return None
    if "json" not in ctype:
        return raw.decode()
    return json.loads(raw)


def render(template: str) -> str:
    """Render a Jinja template on the HA server (POST /api/template)."""
    return rest("POST", "/api/template", {"template": template})


# ----------------------------------------------------------------------- WebSocket
class WS:
    """Tiny RFC6455 client sufficient for HA's JSON websocket API."""

    def __init__(self) -> None:
        u = urllib.parse.urlparse(HA_URL)
        port = u.port or (443 if u.scheme == "https" else 80)
        self.sock = socket.create_connection((u.hostname, port), timeout=60)
        if u.scheme == "https":
            self.sock = ssl.create_default_context().wrap_socket(self.sock, server_hostname=u.hostname)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            (
                f"GET /api/websocket HTTP/1.1\r\nHost: {u.hostname}:{port}\r\nUpgrade: websocket\r\n"
                f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            ).encode()
        )
        hdr = b""
        while b"\r\n\r\n" not in hdr:
            hdr += self.sock.recv(1)
        if b" 101 " not in hdr.split(b"\r\n", 1)[0]:
            raise RuntimeError(f"websocket handshake failed: {hdr[:200]!r}")
        self._id = 0
        assert self.recv()["type"] == "auth_required"
        self.send_raw({"type": "auth", "access_token": token()})
        if self.recv()["type"] != "auth_ok":
            raise RuntimeError("websocket auth failed")

    def _read(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("socket closed")
            buf += chunk
        return buf

    def send_raw(self, msg: dict) -> None:
        payload = json.dumps(msg).encode()
        mask = os.urandom(4)
        head = bytearray([0x81])
        n = len(payload)
        if n < 126:
            head.append(0x80 | n)
        elif n < 65536:
            head.append(0x80 | 126)
            head += struct.pack(">H", n)
        else:
            head.append(0x80 | 127)
            head += struct.pack(">Q", n)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(head) + mask + masked)

    def recv(self) -> dict:
        while True:
            b1, b2 = self._read(2)
            op = b1 & 0x0F
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            if b2 & 0x80:
                self._read(4)
            data = self._read(n)
            if op == 0x9:  # ping
                continue
            if op == 0x8:
                raise ConnectionError("websocket closed by server")
            return json.loads(data)

    def call(self, msg_type: str, **kw: Any) -> Any:
        self._id += 1
        self.send_raw({"id": self._id, "type": msg_type, **kw})
        while True:
            m = self.recv()
            if m.get("id") == self._id and m.get("type") == "result":
                if not m.get("success"):
                    raise RuntimeError(f"{msg_type}: {m.get('error')}")
                return m.get("result")


# ----------------------------------------------------------------------- commands
def cmd_states(pattern: str | None) -> None:
    rx = re.compile(pattern) if pattern else None
    for s in sorted(rest("GET", "/api/states"), key=lambda s: s["entity_id"]):
        if rx and not rx.search(s["entity_id"]):
            continue
        print(f"{s['entity_id']:<60} {s['state']}")


def cmd_entries(domain: str | None) -> None:
    for e in rest("GET", "/api/config/config_entries/entry"):
        if domain and e["domain"] != domain:
            continue
        print(f"{e['entry_id']}  {e['domain']:<18} {e['state']:<12} disabled_by={e.get('disabled_by')}  {e['title']}")


def cmd_entry_disable(entry_id: str, state: str) -> None:
    disabled_by = None if state == "on" else "user"
    print(WS().call("config_entries/disable", entry_id=entry_id, disabled_by=disabled_by))


def cmd_hacs_list(pattern: str) -> None:
    rx = re.compile(pattern, re.I)
    for r in WS().call("hacs/repositories/list", categories=["integration"]):
        if rx.search(r.get("full_name", "")):
            print(json.dumps({k: r.get(k) for k in ("id", "full_name", "installed", "installed_version", "available_version")}))


def cmd_hacs_download(repo_id: str) -> None:
    print(WS().call("hacs/repository/download", repository=repo_id))


def wait_up(timeout: float = 240) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if rest("GET", "/api/", timeout=5).get("message") == "API running.":
                cfg = rest("GET", "/api/config", timeout=5)
                if cfg.get("state") == "RUNNING":
                    print(f"HA back: {cfg['version']} state={cfg['state']}")
                    return
        except Exception:
            pass
        time.sleep(3)
    raise SystemExit("HA did not come back in time")


def cmd_restart() -> None:
    try:
        rest("POST", "/api/services/homeassistant/restart", {}, timeout=10)
    except Exception as e:  # connection usually drops mid-request
        print(f"restart requested ({e.__class__.__name__})")
    time.sleep(10)
    wait_up()


def cmd_flow(handler: str, kv: list[str]) -> None:
    flow = rest("POST", "/api/config/config_entries/flow", {"handler": handler, "show_advanced_options": True})
    print("step:", flow.get("step_id"), "schema:", [f["name"] for f in flow.get("data_schema", [])])
    user_input = {}
    for item in kv:
        k, v = item.split("=", 1)
        user_input[k] = v
    res = rest("POST", f"/api/config/config_entries/flow/{flow['flow_id']}", user_input)
    print(json.dumps({k: res.get(k) for k in ("type", "step_id", "title", "errors", "reason", "result")}, indent=1, default=str))


def cmd_watch(pattern: str, seconds: float) -> None:
    """Poll matching entities every second and print state changes."""
    rx = re.compile(pattern)
    ids = [s["entity_id"] for s in rest("GET", "/api/states") if rx.search(s["entity_id"])]
    last: dict[str, str] = {}
    end = time.time() + seconds
    while time.time() < end:
        for eid in ids:
            st = rest("GET", f"/api/states/{eid}")["state"]
            if last.get(eid) != st:
                print(time.strftime("%H:%M:%S"), f"{eid:<50} -> {st}", flush=True)
                last[eid] = st
        time.sleep(1)


def main(argv: list[str]) -> None:
    if not argv:
        print(__doc__)
        return
    cmd, *args = argv
    if cmd == "states":
        cmd_states(args[0] if args else None)
    elif cmd == "watch":
        cmd_watch(args[0] if args else "helsio", float(args[1]) if len(args) > 1 else 300)
    elif cmd == "entries":
        cmd_entries(args[0] if args else None)
    elif cmd == "entry-disable":
        cmd_entry_disable(args[0], args[1])
    elif cmd == "hacs-list":
        cmd_hacs_list(args[0])
    elif cmd == "hacs-download":
        cmd_hacs_download(args[0])
    elif cmd == "restart":
        cmd_restart()
    elif cmd == "flow":
        cmd_flow(args[0], args[1:])
    elif cmd == "ws":
        print(json.dumps(WS().call(args[0], **(json.loads(args[1]) if len(args) > 1 else {})), indent=1))
    else:
        raise SystemExit(f"unknown command {cmd}\n{__doc__}")


if __name__ == "__main__":
    main(sys.argv[1:])
