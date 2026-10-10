#!/usr/bin/env python3
"""Baut eine kuenstliche Test-ROM aus den extrahierten Code-Dateien (code.zip-Inhalt) und
synthetischen Daten (Texte, Ball-Skripte, Begegnungen). Nur fuer Entwicklungstests.

Aufruf: python tools/dev/make_test_rom.py <code-ordner> <ausgabe.nds> [<daten-ordner>]
Mit <daten-ordner> (entpackte daten.zip mit a/0/5/6 und a/1/2/7) werden diese echten Daten verwendet.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from patch_charms import build_narc, build_text_entry, crypt_words, words_to_raw  # noqa: E402


def mk(lines_text, prefix=False):
    ls = []
    for i, t in enumerate(lines_text):
        w = [(0xF000 if c == "\x01" else 0xBE01 if c == "\x02" else 0 if c == "\x03" else ord(c)) for c in t] + [0xFFFF]
        if prefix:
            w = [0xF000, 0xBD01, 0, 0xF000, 0xFF00, 1, 0xFF] + w
        ls.append([words_to_raw(crypt_words(w, i)), 0])
    return build_text_entry(struct.pack("<HHIII", 1, len(ls), 0, 0, 0x10), ls)


def balls():
    n = 213
    scripts = b""
    for i in range(n):
        item = [17, 2, 575, 50, 93, 4, 23][i % 7]
        scripts += (b"\x2e\x00" + struct.pack("<HHH", 0x2A, 0x8000, item) + struct.pack("<HHH", 0x2A, 0x8001, 1)
                    + struct.pack("<HHH", 0x2A, 0x8002, 0x0B04 + i) + struct.pack("<HH", 0x1C, 2811)
                    + struct.pack("<HHH", 0x30, 0x2F, 0x02))
    head = b"".join(struct.pack("<I", 4 * n - 4 + 26 * i) for i in range(n))
    return head + scripts + b"\x13\xfd"


def wild_entry(seed, blocks):
    out = b""
    for b in range(blocks):
        blk = bytearray(232)
        blk[0] = 10
        for s in range(56):
            sp = 1 + (seed * 31 + b * 7 + s * 3) % 640 if s % 5 else 0
            struct.pack_into("<HBB", blk, 8 + 4 * s, sp, 5 + s % 10, 8 + s % 10)
        out += bytes(blk)
    return out


def main(code_dir, out_path, data_dir=None):
    btnf = b"BTNF" + struct.pack("<I", 16) + struct.pack("<IHH", 4, 0, 1)
    ents2 = [mk([f"Item{k}-{i}" + ("\x01\x02\x03" if (k + i) % 7 == 0 else "") for i in range(200)],
                prefix=(k == 481)) for k in range(483)]
    ents3 = [mk([f"Dialog{k}-{i}" + ("\x01\x02\x03" if i % 2 == 0 else "") for i in range(30)]) for k in range(40)]
    ents5 = [b"\x13\xfd\x00\x00"] * 1241 + [balls()] + [b"\x13\xfd\x00\x00"] * 3
    ents7 = [wild_entry(k, 4 if k % 11 == 0 else 1) for k in range(20)]
    if data_dir:
        def real(path, n):
            return [open(os.path.join(data_dir, path, f"entry_{i:04d}.bin"), "rb").read() for i in range(n)]
        ents5 = real("a/0/5/6", 1289)
        ents7 = real("a/1/2/7", 135)
    files = [build_narc(e, btnf) for e in (ents2, ents3, ents5, ents7)]  # file ids 0..3

    def d(sub, first, parent):
        return struct.pack("<IHH", sub, first, parent)

    def sd(name, did):
        return bytes([0x80 | len(name)]) + name.encode() + struct.pack("<H", did)

    def sf(name):
        return bytes([len(name)]) + name.encode()
    # Verzeichnisse: F000 root, F001 a, F002 a/0, F003 a/0/0, F004 a/0/5, F005 a/1, F006 a/1/2
    subs = [sd("a", 0xF001) + b"\0",
            sd("0", 0xF002) + sd("1", 0xF005) + b"\0",
            sd("0", 0xF003) + sd("5", 0xF004) + b"\0",
            sf("2") + sf("3") + b"\0",
            sf("6") + b"\0",
            sd("2", 0xF006) + b"\0",
            sf("7") + b"\0"]
    firsts = [0, 0, 0, 0, 2, 3, 3]
    parents = [7, 0xF000, 0xF001, 0xF002, 0xF002, 0xF001, 0xF005]
    off = 7 * 8
    table = b""
    for sub, first, parent in zip(subs, firsts, parents):
        table += d(off, first, parent)
        off += len(sub)
    fnt = table + b"".join(subs)

    ov36 = open(os.path.join(code_dir, "overlays", "ov_0036.bin"), "rb").read()
    ov316 = open(os.path.join(code_dir, "overlays", "ov_0316.bin"), "rb").read()
    a9 = open(os.path.join(code_dir, "arm9.bin"), "rb").read()
    blobs = files + [ov36, ov316]  # file ids 0..5
    total = 0x8000 + sum(len(b) + 0x200 for b in blobs) + len(a9) + 0x2000
    rom = bytearray(total)
    rom[0x400:0x400 + len(fnt)] = fnt
    struct.pack_into("<II", rom, 0x40, 0x400, len(fnt))
    struct.pack_into("<II", rom, 0x50, 0x2000, 317 * 32)
    struct.pack_into("<IIIIIIII", rom, 0x2000 + 36 * 32, 36, 0x217F600, 0x561A0, 0x10040,
                     0x21D4B10, 0x21D4B14, 4, 0x303E958)
    struct.pack_into("<IIIIIIII", rom, 0x2000 + 316 * 32, 316, 0x219CE80, 0x2FA0, 0,
                     0x219FDEC, 0x219FDF0, 5, 0x300274C)
    struct.pack_into("<II", rom, 0x48, 0x800, 8 * len(blobs))
    pos = 0x8000
    for i, b in enumerate(blobs):
        struct.pack_into("<II", rom, 0x800 + 8 * i, pos, pos + len(b))
        rom[pos:pos + len(b)] = b
        pos += len(b) + 0x200
    struct.pack_into("<IIII", rom, 0x20, pos, 0x2004800, 0x2004000, len(a9))
    rom[pos:pos + len(a9)] = a9
    struct.pack_into("<I", rom, 0x80, len(rom))
    with open(out_path, "wb") as f:
        f.write(rom)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
