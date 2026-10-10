#!/usr/bin/env python3
"""Packt ausgewaehlte NARC-Archive der ROM Eintrag fuer Eintrag in eine ZIP-Datei (nur lesend).

Aufruf:  python tools/extract_narcs.py "rom.nds" daten.zip a/0/5/6 a/1/2/6 ...
Jeder Eintrag landet als <pfad>/entry_<nr>.bin in der ZIP, dazu eine Datei index.txt.
"""
import os
import struct
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dump_items import read_narc  # noqa: E402
from inspect_nds import parse_fnt, u32  # noqa: E402


def main(src, dst, paths):
    with open(src, "rb") as f:
        rom = f.read()
    fnt = parse_fnt(rom, u32(rom, 0x40), u32(rom, 0x44))
    by_path = {p: i for i, p in fnt.items()}
    fat = u32(rom, 0x48)
    index = []
    with zipfile.ZipFile(dst, "x", zipfile.ZIP_DEFLATED) as z:
        for p in paths:
            if p not in by_path:
                print(f"nicht gefunden: {p}")
                continue
            s, e = struct.unpack_from("<II", rom, fat + by_path[p] * 8)
            entries = read_narc(rom, s, e)
            for n, d in enumerate(entries):
                z.writestr(f"{p}/entry_{n:04d}.bin", d)
            index.append(f"{p}: {len(entries)} Eintraege, {e - s} Bytes")
        z.writestr("index.txt", "\n".join(index) + "\n")
    print("\n".join(index))
    print(f"Fertig: {dst} ({os.path.getsize(dst) / 1048576:.1f} MiB)")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
