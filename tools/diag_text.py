#!/usr/bin/env python3
"""Diagnose: gibt Header-Bytes der Text-Archive aus a/0/0/2 aus (nur lesend, kurz).

Aufruf:  python tools/diag_text.py rom.nds > diag.txt
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dump_items import read_narc  # noqa: E402
from inspect_nds import parse_fnt, u16, u32  # noqa: E402


def main(path):
    with open(path, "rb") as f:
        rom = f.read()
    paths = parse_fnt(rom, u32(rom, 0x40), u32(rom, 0x44))
    fid = next(i for i, p in paths.items() if p == "a/0/0/2")
    s, e = struct.unpack_from("<II", rom, u32(rom, 0x48) + fid * 8)
    entries = read_narc(rom, s, e)
    print(f"{len(entries)} Eintraege")
    print("Uebersicht id:groesse:u16@0:u16@2")
    row = []
    for i, d in enumerate(entries):
        row.append(f"{i}:{len(d)}:{u16(d, 0) if len(d) > 1 else '-'}:{u16(d, 2) if len(d) > 3 else '-'}")
        if len(row) == 6:
            print("  ".join(row))
            row = []
    if row:
        print("  ".join(row))
    print("\nErste 64 Bytes (Hex) einiger Eintraege:")
    for i in (0, 1, 2, 3, 10, 64, 100, 200):
        if i < len(entries):
            print(f"{i}: {entries[i][:64].hex()}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
