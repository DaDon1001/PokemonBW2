#!/usr/bin/env python3
"""Zeigt einige Zeilen der Item-Text-Archive (a/0/0/2, Eintraege 63/64/481/482).

Aufruf:  python tools/dump_text.py rom.nds > text.txt
Zeigt Zeilen 0-1, 17, 149-152 und 179-182 je Eintrag, vollstaendig und mit Steuercodes.
Die Zeilentabelle liegt bei dieser ROM im Klartext, der Zeilenschluessel ist
0x7C89 + 0x2983 * Zeilennummer (aus den Daten abgeleitet).
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dump_items import read_narc  # noqa: E402
from inspect_nds import parse_fnt, u16, u32  # noqa: E402

TEXT_NARC = "a/0/0/2"
ENTRIES = (63, 64, 481, 482)
SHOW = (0, 1, 17, 149, 150, 151, 152, 179, 180, 181, 182)


def rol3(k):
    return ((k << 3) | (k >> 13)) & 0xFFFF


def to_str(chars):
    s = []
    for c in chars:
        if c == 0xFFFF:
            break
        s.append(chr(c) if 0x20 <= c < 0x3000 else f"<{c:04X}>")
    return "".join(s)


def decode_line(data, base, i):
    off, ln = struct.unpack_from("<IH", data, base + 4 + i * 8)
    raw = data[base + off:base + off + ln * 2]
    key = (0x7C89 + 0x2983 * i) & 0xFFFF
    chars = []
    for j in range(0, len(raw) - 1, 2):
        chars.append((raw[j] | raw[j + 1] << 8) ^ key)
        key = rol3(key)
    return to_str(chars)


def main(path):
    with open(path, "rb") as f:
        rom = f.read()
    paths = parse_fnt(rom, u32(rom, 0x40), u32(rom, 0x44))
    fid = next(i for i, p in paths.items() if p == TEXT_NARC)
    s, e = struct.unpack_from("<II", rom, u32(rom, 0x48) + fid * 8)
    entries = read_narc(rom, s, e)
    for idx in ENTRIES:
        data = entries[idx]
        nlines, base = u16(data, 2), u32(data, 0x0C)
        print(f"\n== Eintrag {idx}: {nlines} Zeilen, Block bei {base:#x}")
        for n in SHOW:
            if n < nlines:
                print(f"{n:3d}: {decode_line(data, base, n)[:400]}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
