#!/usr/bin/env python3
"""Benennt vier Beeren in Charms um (Name + Beschreibung) und schreibt eine NEUE ROM.

Aufruf:  python tools/patch_charms.py "original.nds" "neue_rom.nds"
Die Original-ROM wird nur gelesen. Es aendert sich nur das Text-Archiv a/0/0/2
(Eintraege 63, 64, 481, 482; Zeilen 179-182). Die Effekte der Charms sind NICHT enthalten.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dump_items import read_narc  # noqa: E402
from inspect_nds import crc16, parse_fnt, u16, u32  # noqa: E402

TEXT_NARC = "a/0/0/2"
NAME_ENTRIES = (64, 481, 482)
DESC_ENTRY = 63
PREFIX_END = 0x00FF  # Eintrag 481: Steuercode-Vorspann endet mit diesem Zeichen

CHARMS = {  # Zeile: (Name, Beschreibung)
    179: ("Shiny Charm",
          "Makes the next wild Pokémon you\nmeet shiny. Used up after one\nencounter."),
    180: ("100% IV Charm",
          "Makes the next wild Pokémon you\nmeet have perfect IVs. Used up\nafter one encounter."),
    181: ("Legendary Charm",
          "Makes the next wild encounter a\nlegendary Pokémon. Used up after\none encounter."),
    182: ("Static Charm",
          "Makes the next wild Pokémon have\n600+ base stats, like a static\nencounter. Used up after use."),
}


def rol3(k):
    return ((k << 3) | (k >> 13)) & 0xFFFF


def crypt_words(words, line):
    """Ver-/Entschluesselung (XOR ist symmetrisch). Schluessel = 0x7C89 + 0x2983 * Zeile."""
    key = (0x7C89 + 0x2983 * line) & 0xFFFF
    out = []
    for w in words:
        out.append(w ^ key)
        key = rol3(key)
    return out


def raw_to_words(raw):
    return list(struct.unpack(f"<{len(raw) // 2}H", raw))


def words_to_raw(words):
    return struct.pack(f"<{len(words)}H", *words)


def text_to_words(text):
    return [0xFFFE if ch == "\n" else ord(ch) for ch in text] + [0xFFFF]


def parse_text_entry(data):
    nlines, base = u16(data, 2), u32(data, 0x0C)
    lines = []
    for i in range(nlines):
        off, ln, unk = struct.unpack_from("<IHH", data, base + 4 + i * 8)
        lines.append([data[base + off:base + off + ln * 2], unk])
    return data[:0x10], lines


def build_text_entry(header, lines):
    n = len(lines)
    table, body, pos = b"", b"", 4 + n * 8
    for raw, unk in lines:
        table += struct.pack("<IHH", pos, len(raw) // 2, unk)
        body += raw
        pos += len(raw)
    block = struct.pack("<I", pos) + table + body
    head = bytearray(header)
    struct.pack_into("<I", head, 4, len(block))
    return bytes(head) + block


def patch_entry(data, idx, new_by_line):
    header, lines = parse_text_entry(data)
    for line, text in new_by_line.items():
        new_words = text_to_words(text)
        if idx == 481:  # Vorspann der Originalzeile uebernehmen
            old = crypt_words(raw_to_words(lines[line][0]), line)
            prefix = old[:len(old) - old[::-1].index(PREFIX_END)] if PREFIX_END in old else []
            new_words = prefix + new_words
        lines[line][0] = words_to_raw(crypt_words(new_words, line))
    return build_text_entry(header, lines)


def parse_narc_blocks(rom, start):
    hdr = u16(rom, start + 0x0C)
    btaf = start + hdr
    btnf = btaf + u32(rom, btaf + 4)
    btnf_end = btnf + u32(rom, btnf + 4)
    return bytes(rom[btnf:btnf_end])


def build_narc(entries, btnf):
    gm, offs = bytearray(), []
    for e in entries:
        gm += b"\0" * (-len(gm) % 4)
        offs.append((len(gm), len(gm) + len(e)))
        gm += e
    gm += b"\0" * (-len(gm) % 4)
    n = len(entries)
    btaf = b"BTAF" + struct.pack("<IHH", 12 + 8 * n, n, 0) + b"".join(struct.pack("<II", a, b) for a, b in offs)
    gmif = b"GMIF" + struct.pack("<I", 8 + len(gm)) + bytes(gm)
    total = 0x10 + len(btaf) + len(btnf) + len(gmif)
    return b"NARC" + struct.pack("<HHIHH", 0xFFFE, 0x0100, total, 0x10, 3) + btaf + btnf + gmif


def find_text_narc(rom):
    paths = parse_fnt(rom, u32(rom, 0x40), u32(rom, 0x44))
    fid = next((i for i, p in paths.items() if p == TEXT_NARC), None)
    if fid is None:
        sys.exit(f"{TEXT_NARC} nicht gefunden")
    s, e = struct.unpack_from("<II", rom, u32(rom, 0x48) + fid * 8)
    return fid, s, e


def patch_rom(rom):
    fid, s, e = find_text_narc(rom)
    entries = read_narc(rom, s, e)
    btnf = parse_narc_blocks(rom, s)
    names = {ln: v[0] for ln, v in CHARMS.items()}
    descs = {ln: v[1] for ln, v in CHARMS.items()}
    new_entries = list(entries)
    for idx in NAME_ENTRIES:
        new_entries[idx] = patch_entry(entries[idx], idx, names)
    new_entries[DESC_ENTRY] = patch_entry(entries[DESC_ENTRY], DESC_ENTRY, descs)
    narc = build_narc(new_entries, btnf)

    out = bytearray(rom)
    used = u32(rom, 0x80)
    pos = max(len(rom), used)
    pos += -pos % 0x200
    out += b"\0" * (pos - len(out))
    out += narc
    struct.pack_into("<II", out, u32(rom, 0x48) + fid * 8, pos, pos + len(narc))
    struct.pack_into("<I", out, 0x80, pos + len(narc))
    struct.pack_into("<H", out, 0x15E, crc16(bytes(out[:0x15E])))
    return bytes(out), entries, new_entries


def verify(new_rom, old_entries, new_entries):
    fid, s, e = find_text_narc(new_rom)
    got = read_narc(new_rom, s, e)
    assert len(got) == len(new_entries), "Eintragszahl falsch"
    changed = set(NAME_ENTRIES) | {DESC_ENTRY}
    for i, (g, n, o) in enumerate(zip(got, new_entries, old_entries)):
        assert g == n, f"Eintrag {i} nach dem Schreiben anders"
        if i not in changed:
            assert g == o, f"Eintrag {i} ungewollt veraendert"
    assert u16(new_rom, 0x15E) == crc16(new_rom[:0x15E]), "Header-CRC falsch"


def main(src, dst):
    if os.path.abspath(src) == os.path.abspath(dst):
        sys.exit("Ziel darf nicht die Original-ROM sein.")
    with open(src, "rb") as f:
        rom = f.read()
    new_rom, old_entries, new_entries = patch_rom(rom)
    verify(new_rom, old_entries, new_entries)
    with open(dst, "xb") as f:
        f.write(new_rom)
    print(f"Fertig: {dst} ({len(new_rom)} Bytes). Original unveraendert.")
    for ln, (name, _) in CHARMS.items():
        print(f"  Zeile {ln}: {name}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
