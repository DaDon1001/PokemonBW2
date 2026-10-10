#!/usr/bin/env python3
"""Sucht Woerter in allen Texten von a/0/0/2 und gibt Fundstellen aus (nur lesend).

Aufruf:  python tools/find_text.py rom.nds Begriff1 Begriff2 ... > fund.txt
Ausgabe: je Archiv die ersten 3 Treffer (Archiv-Nummer, Zeilennummer, Zeile) und eine Uebersicht.
Gross-/Kleinschreibung wird ignoriert.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dump_items import read_narc  # noqa: E402
from dump_text import decode_line  # noqa: E402
from inspect_nds import parse_fnt, u16, u32  # noqa: E402

MAX_PER_ARCHIVE = 3


def main(path, terms):
    with open(path, "rb") as f:
        rom = f.read()
    paths = parse_fnt(rom, u32(rom, 0x40), u32(rom, 0x44))
    fid = next(i for i, p in paths.items() if p == "a/0/0/2")
    s, e = struct.unpack_from("<II", rom, u32(rom, 0x48) + fid * 8)
    entries = read_narc(rom, s, e)
    low = [t.lower() for t in terms]
    summary = []
    for idx, data in enumerate(entries):
        if len(data) < 0x14 or u16(data, 0) != 1:
            continue
        n, base = u16(data, 2), u32(data, 0x0C)
        if n == 0 or base + 4 + n * 8 > len(data):
            continue
        shown = total = 0
        for i in range(n):
            try:
                text = decode_line(data, base, i)
            except Exception:
                break
            if any(w in text.lower() for w in low):
                total += 1
                if shown < MAX_PER_ARCHIVE:
                    print(f"Archiv {idx} ({n} Zeilen), Zeile {i}: {text[:140]}")
                    shown += 1
        if total:
            summary.append((idx, n, total))
    print("\nUebersicht (Archiv: Zeilen im Archiv, Treffer):")
    print("; ".join(f"{i}: {n} Z., {t} Tr." for i, n, t in summary))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2:])
