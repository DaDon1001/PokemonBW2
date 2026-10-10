#!/usr/bin/env python3
"""Gibt alle Zeilen einzelner Text-Archive aus a/0/0/2 aus (nur lesend).

Aufruf:  python tools/dump_entry.py rom.nds 40 > archiv40.txt
         (mehrere Archiv-Nummern moeglich: ... 40 41)
         Mit Zeilenbereich: ... 384:0-60   (nur Zeilen 0 bis 60 von Archiv 384)
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dump_items import read_narc  # noqa: E402
from dump_text import decode_line  # noqa: E402
from inspect_nds import parse_fnt, u16, u32  # noqa: E402


def main(path, idxs):
    with open(path, "rb") as f:
        rom = f.read()
    paths = parse_fnt(rom, u32(rom, 0x40), u32(rom, 0x44))
    fid = next(i for i, p in paths.items() if p == "a/0/0/2")
    s, e = struct.unpack_from("<II", rom, u32(rom, 0x48) + fid * 8)
    entries = read_narc(rom, s, e)
    for spec in idxs:
        idx, _, rng = spec.partition(":")
        idx = int(idx)
        data = entries[idx]
        n, base = u16(data, 2), u32(data, 0x0C)
        lo, hi = 0, n - 1
        if rng:
            a, _, b = rng.partition("-")
            lo, hi = int(a), min(int(b or a), n - 1)
        print(f"== Archiv {idx}: {n} Zeilen (gezeigt: {lo}-{hi})")
        for i in range(lo, hi + 1):
            print(f"{i:3d}: {decode_line(data, base, i)[:200]}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2:])
