#!/usr/bin/env python3
"""Gibt die Rohdaten einzelner Item-Eintraege aus a/0/2/4 als Hex aus (nur lesend).

Aufruf:  python tools/dump_items.py rom.nds > items.txt
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inspect_nds import parse_fnt, u16, u32  # noqa: E402

ITEM_NARC = "a/0/2/4"
# Referenz-Items (Meisterball, Pokeball, Trank) und der Berry-Bereich 149..212
IDS = [0, 1, 4, 17] + list(range(149, 213))


def read_narc(rom, start, end):
    """Gibt eine Liste mit den Bytes jedes NARC-Eintrags zurueck."""
    if rom[start:start + 4] != b"NARC":
        raise ValueError("kein NARC")
    btaf = start + u16(rom, start + 0x0C)
    if rom[btaf:btaf + 4] != b"BTAF":
        raise ValueError("BTAF nicht gefunden")
    count = u16(rom, btaf + 8)
    btnf = btaf + u32(rom, btaf + 4)
    gmif = btnf + u32(rom, btnf + 4)
    base = gmif + 8
    return [rom[base + u32(rom, btaf + 12 + i * 8):base + u32(rom, btaf + 16 + i * 8)]
            for i in range(count)]


def main(path):
    with open(path, "rb") as f:
        rom = f.read()
    fat_off, fat_size = u32(rom, 0x48), u32(rom, 0x4C)
    paths = parse_fnt(rom, u32(rom, 0x40), u32(rom, 0x44))
    fid = next((i for i, p in paths.items() if p == ITEM_NARC), None)
    if fid is None:
        sys.exit(f"{ITEM_NARC} nicht gefunden")
    s, e = struct.unpack_from("<II", rom, fat_off + fid * 8)
    entries = read_narc(rom, s, e)
    sizes = sorted({len(x) for x in entries})
    print(f"{ITEM_NARC}: {len(entries)} Eintraege, Groessen: {sizes}")
    for i in IDS:
        if i < len(entries):
            print(f"{i:3d}: {entries[i].hex()}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
