#!/usr/bin/env python3
"""Sucht in den Text-Archiven (a/0/0/2) nach Beeren-Namen und gibt Fundstellen aus.

Aufruf:  python tools/dump_text.py rom.nds > text.txt
Gibt nur kurze Fundstellen aus (Archiv-Nummer, Zeilennummer, Text), keine ganzen Texte.
"""
import itertools
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dump_items import read_narc  # noqa: E402
from inspect_nds import parse_fnt, u16, u32  # noqa: E402

TEXT_NARC = "a/0/0/2"
SEARCH = ["Spelon Berry", "Pamtre Berry", "Watmel Berry", "Durin Berry", "Cheri Berry"]
KEYS = (0x2983, 0x7C89)


def rol3(k):
    return ((k << 3) | (k >> 13)) & 0xFFFF


def decode_text(raw, i, key0):
    key = key0
    out = []
    for j in range(0, len(raw) - 1, 2):
        c = (raw[j] | raw[j + 1] << 8) ^ key
        key = rol3(key)
        out.append(c)
    return out


def to_str(chars):
    s = []
    for c in chars:
        if c == 0xFFFF:
            break
        s.append(chr(c) if 0x20 <= c < 0x3000 else f"<{c:04X}>")
    return "".join(s)


def decode_entry(data, tkey_base, skey_base):
    """Gibt Liste der Zeilen (als Text) oder None, falls der Aufbau nicht passt."""
    if len(data) < 0x14:
        return None
    nblocks, nlines = u16(data, 0), u16(data, 2)
    if nblocks != 1 or nlines == 0 or nlines > 5000:
        return None
    base = u32(data, 0x0C)
    if base + 4 + nlines * 8 > len(data):
        return None
    lines = []
    for i in range(nlines):
        tk = (tkey_base * (i + 1)) & 0xFFFF
        off, ln = struct.unpack_from("<IH", data, base + 4 + i * 8)
        off ^= tk | tk << 16
        ln ^= tk
        if ln > 4000 or base + off + ln * 2 > len(data):
            return None
        raw = data[base + off:base + off + ln * 2]
        lines.append(to_str(decode_text(raw, i, (skey_base * (i + 1)) & 0xFFFF)))
    return lines


def main(path):
    with open(path, "rb") as f:
        rom = f.read()
    paths = parse_fnt(rom, u32(rom, 0x40), u32(rom, 0x44))
    fid = next((i for i, p in paths.items() if p == TEXT_NARC), None)
    if fid is None:
        sys.exit(f"{TEXT_NARC} nicht gefunden")
    fat_off = u32(rom, 0x48)
    s, e = struct.unpack_from("<II", rom, fat_off + fid * 8)
    entries = read_narc(rom, s, e)
    print(f"{TEXT_NARC}: {len(entries)} Eintraege")

    # Schluessel-Kombination suchen: die, mit der die meisten Eintraege gueltig dekodieren
    best = None
    for tk, sk in itertools.product(KEYS, KEYS):
        ok = sum(1 for d in entries[:80] if decode_entry(d, tk, sk))
        if best is None or ok > best[0]:
            best = (ok, tk, sk)
    print(f"Gewaehlte Schluessel: tabelle={best[1]:#x} text={best[2]:#x} (gueltige Eintraege in den ersten 80: {best[0]})")
    _, tk, sk = best

    decoded = {i: decode_entry(d, tk, sk) for i, d in enumerate(entries)}
    name_entry = None
    for i, lines in decoded.items():
        if not lines:
            continue
        hits = [(n, t) for term in SEARCH for n, t in enumerate(lines) if t == term]
        if hits:
            print(f"Eintrag {i}: {len(lines)} Zeilen; Treffer: {hits}")
            if name_entry is None:
                name_entry = (i, len(lines))
    if name_entry is None:
        print("Keine Treffer. Dekodierung hat vermutlich nicht gepasst.")
        # Diagnose: ein paar Zeilen eines Eintrags zeigen
        for i, lines in decoded.items():
            if lines:
                print(f"Beispiel Eintrag {i}: {lines[:3]}")
                break
        return
    # Beschreibungen: Eintraege mit gleicher Zeilenzahl, Zeile 179 anzeigen
    print("Zeile 179..182 in Eintraegen mit gleicher Zeilenzahl:")
    for i, lines in decoded.items():
        if lines and len(lines) == name_entry[1]:
            print(f"Eintrag {i}: " + " | ".join(lines[n][:60] for n in range(179, 183)))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
