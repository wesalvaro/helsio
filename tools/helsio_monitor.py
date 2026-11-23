#!/usr/bin/env python3
"""Log the Helsio's ECHONET Lite state over time (for decoding Sharp vendor props).

Listens for INF (push) frames from the oven and polls a set of EPCs every
--interval seconds. Each sample is one CSV row; only rows whose values changed
are printed by default (use --all to keep every poll).

Usage:
  tools/helsio_monitor.py [--host IP] [--interval 5] [--out log.csv] [--all]

Host defaults to $HELSIO_HOST or multicast discovery.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import select
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from echonet import oven_host  # noqa: E402

PORT = 3610
MCAST = "224.0.23.0"
CTRL = bytes.fromhex("05FF01")
OVEN = bytes.fromhex("03B801")
EPCS = [0x80, 0xB0, 0xB1, 0xB2, 0xE1, 0xE6, 0x85, 0xF0, 0xF1, 0xF2]

HEATING = {
    0x40: "idle", 0x41: "heating", 0x42: "suspended", 0x43: "done",
    0x44: "setting", 0x45: "preheating", 0x46: "preheat_hold", 0x47: "manual_stop",
}


def parse(d: bytes):
    """Return (tid, seoj, esv, {epc: edt})."""
    if len(d) < 12 or d[:2] != b"\x10\x81":
        return None
    opc = d[11]
    i = 12
    props = {}
    for _ in range(opc):
        if i + 2 > len(d):
            break
        epc, pdc = d[i], d[i + 1]
        props[epc] = d[i + 2 : i + 2 + pdc]
        i += 2 + pdc
    return d[2:4], d[4:7], d[10], props


def get_frame(tid: int, epcs: list[int]) -> bytes:
    body = bytes([0x62, len(epcs)]) + b"".join(bytes([e, 0]) for e in epcs)
    return b"\x10\x81" + tid.to_bytes(2, "big") + CTRL + OVEN + body


def fmt(epc: int, edt: bytes) -> str:
    if edt is None:
        return ""
    if epc == 0xB1 and len(edt) == 1:
        return HEATING.get(edt[0], f"0x{edt[0]:02X}")
    if epc == 0xB0 and len(edt) == 1:
        return {0x41: "open", 0x42: "closed"}.get(edt[0], f"0x{edt[0]:02X}")
    if epc == 0xE6 and len(edt) == 3:
        return f"{edt[0]:02d}:{edt[1]:02d}:{edt[2]:02d}"
    if epc == 0x85 and len(edt) == 4:
        return str(int.from_bytes(edt, "big"))
    return edt.hex()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=None, help="oven IP (default: $HELSIO_HOST or discovery)")
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--out", default="-")
    ap.add_argument("--all", action="store_true", help="log every poll, not only changes")
    args = ap.parse_args()
    args.host = oven_host(args.host)

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("", PORT))
    mreq = socket.inet_aton(MCAST) + socket.inet_aton("0.0.0.0")
    s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    s.setblocking(False)

    out = sys.stdout if args.out == "-" else open(args.out, "a", newline="")
    w = csv.writer(out)
    cols = ["time", "kind"] + [f"{e:02X}" for e in EPCS]
    w.writerow(cols)
    out.flush()

    state: dict[int, bytes] = {}
    last_row = None
    tid = 0
    next_poll = 0.0

    def emit(kind: str, changed: dict[int, bytes]) -> None:
        nonlocal last_row
        state.update(changed)
        row = [dt.datetime.now().isoformat(timespec="seconds"), kind] + [fmt(e, state.get(e)) for e in EPCS]
        if args.all or kind == "INF" or row[2:] != (last_row[2:] if last_row else None):
            w.writerow(row)
            out.flush()
            last_row = row

    print(f"# monitoring {args.host}; Ctrl-C to stop", file=sys.stderr)
    while True:
        now = time.time()
        if now >= next_poll:
            tid = (tid + 1) & 0xFFFF
            s.sendto(get_frame(tid, EPCS), (args.host, PORT))
            next_poll = now + args.interval
        r, _, _ = select.select([s], [], [], max(0.0, next_poll - now))
        if not r:
            continue
        data, addr = s.recvfrom(4096)
        if addr[0] != args.host:
            continue
        p = parse(data)
        if not p:
            continue
        _, seoj, esv, props = p
        if seoj != OVEN:
            continue
        if esv == 0x73:  # INF
            emit("INF", props)
        elif esv in (0x72, 0x52):  # Get_Res / Get_SNA
            emit("POLL", props)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
