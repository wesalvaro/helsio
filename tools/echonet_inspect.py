"""Read-only ECHONET Lite inspection of the oven (class 0x03B8).

Usage: echonet_inspect.py [HOST]   (default: $HELSIO_HOST or multicast discovery)
"""
import socket, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from echonet import oven_host  # noqa: E402

IP = oven_host(sys.argv[1] if len(sys.argv) > 1 else None)
print(f"# oven: {IP}")
PORT = 3610
tid = [1]

def frame(deoj, esv, props):
    tid[0] = (tid[0] + 1) & 0xFFFF
    b = bytes([0x10, 0x81]) + tid[0].to_bytes(2, "big") + bytes.fromhex("05FF01") + deoj + bytes([esv, len(props)])
    for epc, edt in props:
        b += bytes([epc, len(edt)]) + edt
    return b

def parse(d):
    out = {}
    opc = d[11]; i = 12
    for _ in range(opc):
        epc, pdc = d[i], d[i+1]; edt = d[i+2:i+2+pdc]; i += 2 + pdc
        out[epc] = edt
    return d[10], out  # esv, props

def get(deoj, epcs, timeout=2.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("", PORT)); s.settimeout(timeout)
    s.sendto(frame(deoj, 0x62, [(e, b"") for e in epcs]), (IP, PORT))
    end = time.time() + timeout
    while time.time() < end:
        try:
            d, a = s.recvfrom(4096)
        except socket.timeout:
            break
        if a[0] == IP and d[2:4] == tid[0].to_bytes(2, "big"):
            s.close(); return parse(d)
    s.close(); return None, {}

def propmap(edt):
    if not edt: return []
    n = edt[0]
    if n < 16: return list(edt[1:1+n])
    res = []
    for i in range(16):
        for bit in range(8):
            if edt[1+i] & (1 << bit): res.append(0x80 + bit*16 + i)
    return sorted(res)

NODE = bytes.fromhex("0EF001"); OVEN = bytes.fromhex("03B801")

esv, p = get(NODE, [0x8A, 0x8C, 0x8D, 0x83, 0x82, 0xD5, 0xD6])
print("== Node profile ==", hex(esv) if esv else None)
for k, v in p.items(): print(f"  {k:02X}: {v.hex()}  {v!r}")

esv, p = get(OVEN, [0x9D, 0x9E, 0x9F])
print("== Oven property maps ==", hex(esv) if esv else None)
maps = {}
for k, v in p.items():
    maps[k] = propmap(v); print(f"  {k:02X}: {' '.join(f'{e:02X}' for e in maps[k])}")

getmap = maps.get(0x9F, [])
print("== Oven GET values ==")
for i in range(0, len(getmap), 6):
    chunk = getmap[i:i+6]
    esv, p = get(OVEN, chunk)
    for e in chunk:
        v = p.get(e)
        print(f"  {e:02X}: {v.hex() if v is not None else '<no reply>'}")
