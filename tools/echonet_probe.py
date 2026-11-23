#!/usr/bin/env python3
"""Discover ECHONET Lite nodes on the LAN and print their object instances."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from echonet import OVEN_CLASS, discover  # noqa: E402

found = discover()
if not found:
    print("no ECHONET Lite responders")
    sys.exit(1)
for ip, eojs in found.items():
    tags = ", ".join(e.hex() + (" (oven)" if e[:2] == OVEN_CLASS else "") for e in eojs)
    print(f"{ip:<16} {tags}")
