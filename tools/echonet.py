"""Shared ECHONET Lite helpers: discovery of the oven and host resolution.

Host precedence: explicit argument > $HELSIO_HOST > multicast discovery of the
first node that advertises a Combination microwave oven (0x03B8).
"""
from __future__ import annotations

import os
import socket
import time

PORT = 3610
MCAST = "224.0.23.0"
OVEN_CLASS = b"\x03\xb8"
# EHD TID SEOJ(controller) DEOJ(node profile) ESV=Get OPC=1 EPC=D6(instance list) PDC=0
INSTANCE_LIST_GET = bytes.fromhex("1081000105FF010EF0016201D600")


def discover(timeout: float = 3.0) -> dict[str, list[bytes]]:
    """Return {ip: [eoj, ...]} for every node answering the instance-list query."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
    s.bind(("", PORT))
    s.settimeout(0.5)
    for _ in range(2):
        s.sendto(INSTANCE_LIST_GET, (MCAST, PORT))
        time.sleep(0.2)
    found: dict[str, list[bytes]] = {}
    end = time.time() + timeout
    while time.time() < end:
        try:
            data, addr = s.recvfrom(2048)
        except socket.timeout:
            continue
        # Get_Res for D6: ... ESV=72 OPC=01 EPC=D6 PDC=n EDT=count + 3-byte EOJs
        if len(data) >= 14 and data[10] == 0x72 and data[12] == 0xD6:
            n = data[14]
            eojs = [data[15 + 3 * i : 18 + 3 * i] for i in range(n)]
            found.setdefault(addr[0], [])
            for e in eojs:
                if e not in found[addr[0]]:
                    found[addr[0]].append(e)
    s.close()
    return found


def find_oven(timeout: float = 3.0) -> str | None:
    for ip, eojs in discover(timeout).items():
        if any(e[:2] == OVEN_CLASS for e in eojs):
            return ip
    return None


def oven_host(explicit: str | None = None) -> str:
    host = explicit or os.environ.get("HELSIO_HOST")
    if host:
        return host
    host = find_oven()
    if not host:
        raise SystemExit("No ECHONET Lite oven found on the LAN; set HELSIO_HOST (see .env.example).")
    return host
