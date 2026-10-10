#!/usr/bin/env python3
"""Baut eine kuenstliche Test-ROM aus den extrahierten Code-Dateien (code.zip-Inhalt) und
synthetischen Text-Archiven. Nur fuer Entwicklungstests.

Aufruf: python tools/dev/make_test_rom.py <code-ordner> <ausgabe.nds>
"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from patch_charms import (build_narc, build_text_entry, crypt_words, words_to_raw)  # noqa: E402


def mk(lines_text, prefix=False):
    ls = []
    for i, t in enumerate(lines_text):
        w = [(0xF000 if c == "\x01" else 0xBE01 if c == "\x02" else 0 if c == "\x03" else ord(c)) for c in t] + [0xFFFF]
        if prefix:
            w = [0xF000, 0xBD01, 0, 0xF000, 0xFF00, 1, 0xFF] + w
        ls.append([words_to_raw(crypt_words(w, i)), 0])
    return build_text_entry(struct.pack("<HHIII", 1, len(ls), 0, 0, 0x10), ls)


def main(code_dir, out_path):
    ents = [mk([f"Item{k}-{i}" + ("\x01\x02\x03" if (k + i) % 7 == 0 else "") for i in range(200)],
               prefix=(k == 481)) for k in range(483)]
    btnf = b"BTNF" + struct.pack("<I", 16) + struct.pack("<IHH", 4, 0, 1)
    narc = build_narc(ents, btnf)
    ents3 = [mk([f"Dialog{k}-{i}" + ("\x01\x02\x03" if i % 2 == 0 else "") for i in range(30)]) for k in range(40)]
    narc3 = build_narc(ents3, btnf)

    def d(sub, first, parent):
        return struct.pack("<IHH", sub, first, parent)
    sub0 = bytes([0x81]) + b"a" + struct.pack("<H", 0xF001) + b"\0"
    sub1 = bytes([0x81]) + b"0" + struct.pack("<H", 0xF002) + b"\0"
    sub2 = bytes([0x81]) + b"0" + struct.pack("<H", 0xF003) + b"\0"
    sub3 = bytes([0x01]) + b"2" + bytes([0x01]) + b"3" + b"\0"
    o0 = 32
    o1 = o0 + len(sub0)
    o2 = o1 + len(sub1)
    o3 = o2 + len(sub2)
    fnt = d(o0, 0, 4) + d(o1, 0, 0xF000) + d(o2, 0, 0xF001) + d(o3, 0, 0xF002) + sub0 + sub1 + sub2 + sub3
    ov = open(os.path.join(code_dir, "overlays", "ov_0036.bin"), "rb").read()
    a9 = open(os.path.join(code_dir, "arm9.bin"), "rb").read()
    rom = bytearray(0x8000 + len(narc) + len(narc3) + len(ov) + len(a9) + 0x2000)
    rom[0x400:0x400 + len(fnt)] = fnt
    struct.pack_into("<II", rom, 0x40, 0x400, len(fnt))
    struct.pack_into("<II", rom, 0x50, 0x2000, 37 * 32)
    struct.pack_into("<IIIIIIII", rom, 0x2000 + 36 * 32, 36, 0x217F600, 0x561A0, 0x10040,
                     0x21D4B10, 0x21D4B14, 2, 0x303E958)
    struct.pack_into("<II", rom, 0x48, 0x800, 24)
    p_narc = 0x8000
    p_narc3 = p_narc + len(narc) + 0x200
    p_ov = p_narc3 + len(narc3) + 0x200
    p_a9 = p_ov + len(ov) + 0x200
    struct.pack_into("<II", rom, 0x800, p_narc, p_narc + len(narc))
    struct.pack_into("<II", rom, 0x808, p_narc3, p_narc3 + len(narc3))
    struct.pack_into("<II", rom, 0x810, p_ov, p_ov + len(ov))
    rom[p_narc:p_narc + len(narc)] = narc
    rom[p_narc3:p_narc3 + len(narc3)] = narc3
    rom[p_ov:p_ov + len(ov)] = ov
    rom[p_a9:p_a9 + len(a9)] = a9
    struct.pack_into("<IIII", rom, 0x20, p_a9, 0x2004800, 0x2004000, len(a9))
    struct.pack_into("<I", rom, 0x80, len(rom))
    with open(out_path, "wb") as f:
        f.write(rom)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
