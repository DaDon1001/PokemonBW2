#!/usr/bin/env python3
"""Charm-Mod: benennt vier Beeren um und gibt dem Shiny Charm seine Wirkung. Schreibt eine NEUE ROM.

Aufruf:  python tools/patch_charms.py "original.nds" "neue_rom.nds"
Die Original-ROM wird nur gelesen. Geaendert werden:
  1. Das Text-Archiv a/0/0/2 (Eintraege 63, 64, 481, 482; Zeilen 179-182): Namen/Beschreibungen.
  2. Das Overlay 36 (Kampf): Shiny Charm (Item 179). Beim naechsten wilden Pokemon wird ein
     Charm aus dem Beutel verbraucht und das Pokemon ist (fast sicher) shiny.
Die anderen drei Charms haben noch keine Wirkung.
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

# --- Shiny-Charm-Patch in Overlay 36 (Funktion, die wilde Pokemon fuer den Kampf erzeugt) ---
OV_ID = 36
OV_PATCH_ADDR = 0x021A0DD6
# Original: Beutel holen, Item 0x278 (Schluesselitem Shiny Charm) pruefen, Wuerfelzahl 1 bzw. 3
OV_ORIGINAL = bytes.fromhex("2868012676f6bbfa9e2189000122042367f645fb002800d0b61c301c")
# Neu: Beutel holen, 1x Item 179 entfernen; war es da, Wuerfelzahl 130560 statt 1
OV_NEW = bytes.fromhex("286876f6bcfab3210122042367f623fb0126002801d0ff267602301c")
OV_RAM_ADDR = 0x0217F600
OV_RAM_SIZE = 0x561A0

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


def blz_decompress(data):
    """Entpackt ein BLZ-komprimiertes Overlay (rueckwaerts laufender LZ77)."""
    inc = u32(data, len(data) - 4)
    if inc == 0:
        return bytes(data)
    hdr = data[-5]
    enc = u32(data, len(data) - 8) & 0xFFFFFF
    dec = len(data) - enc
    raw = bytearray(len(data) + inc)
    raw[:dec] = data[:dec]
    pak, rp, mask, flags = len(data) - hdr, len(raw), 0, 0
    while rp > dec:
        if mask == 0:
            pak -= 1
            flags, mask = data[pak], 0x80
        if flags & mask:
            pak -= 2
            b1, b0 = data[pak + 1], data[pak]
            length, pos = (b1 >> 4) + 3, (((b1 & 0xF) << 8) | b0) + 3
            for _ in range(length):
                rp -= 1
                raw[rp] = raw[rp + pos]
                if rp <= dec:
                    break
        else:
            pak -= 1
            rp -= 1
            raw[rp] = data[pak]
        mask >>= 1
    return bytes(raw)


def read_overlay(rom, ov_id):
    """Gibt (Tabellenoffset, file_id, entpackte Daten) zurueck."""
    ov_off = u32(rom, 0x50) + ov_id * 32
    fid = u32(rom, ov_off + 24)
    s, e = struct.unpack_from("<II", rom, u32(rom, 0x48) + fid * 8)
    return ov_off, fid, blz_decompress(rom[s:e])


def patch_overlay(rom):
    """Gibt das gepatchte, unkomprimierte Overlay 36 zurueck (oder bricht ab, wenn es nicht passt)."""
    ov_off, fid, ov = read_overlay(rom, OV_ID)
    if u32(rom, ov_off + 4) != OV_RAM_ADDR or len(ov) != OV_RAM_SIZE:
        sys.exit("Overlay 36 hat nicht die erwartete Groesse/Adresse. Diese ROM-Version passt nicht.")
    off = OV_PATCH_ADDR - OV_RAM_ADDR
    if ov[off:off + len(OV_ORIGINAL)] != OV_ORIGINAL:
        sys.exit("Die Code-Stelle im Overlay 36 passt nicht zum erwarteten Original. "
                 "Diese ROM-Version (oder schon gepatcht?) wird nicht unterstuetzt. Nichts geschrieben.")
    return ov[:off] + OV_NEW + ov[off + len(OV_NEW):]


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
    ov_new = patch_overlay(rom)

    out = bytearray(rom)
    pos = max(len(rom), u32(rom, 0x80))
    for file_id, blob in ((fid, narc), (None, ov_new)):
        pos += -pos % 0x200
        out += b"\0" * (pos - len(out))
        out += blob
        if file_id is None:  # Overlay 36: unkomprimiert, FAT und Overlay-Tabelle anpassen
            ov_off = u32(rom, 0x50) + OV_ID * 32
            ov_fid = u32(rom, ov_off + 24)
            struct.pack_into("<II", out, u32(rom, 0x48) + ov_fid * 8, pos, pos + len(blob))
            struct.pack_into("<I", out, ov_off + 28, 0x02000000)
        else:
            struct.pack_into("<II", out, u32(rom, 0x48) + file_id * 8, pos, pos + len(blob))
        pos += len(blob)
    struct.pack_into("<I", out, 0x80, pos)
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
    _, _, ov = read_overlay(new_rom, OV_ID)
    off = OV_PATCH_ADDR - OV_RAM_ADDR
    assert len(ov) == OV_RAM_SIZE and ov[off:off + len(OV_NEW)] == OV_NEW, "Overlay-Patch nicht korrekt"


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
    print("Shiny Charm (Item 179): wirkt beim naechsten wilden Pokemon.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
