#!/usr/bin/env python3
"""Charm-Mod fuer Pokemon Schwarz 2: vier Beeren werden zu Charms. Schreibt eine NEUE ROM.

Aufruf:  python tools/patch_charms.py "original.nds" "neue_rom.nds" [--test-items A,B,C,D] [--find-rate N]
  --find-rate N: Fundchance. Jedes wilde Pokemon traegt mit Chance 1 zu N einen zufaelligen Charm
      als Item (Standard 20). Zum Testen z. B. 1 (jedes wilde Pokemon traegt einen Charm).
  --test-items A,B,C,D: Test-Variante. Statt der Beeren (179-182) werden vier andere Item-IDs
      (1-255) als Charms benutzt, z. B. 17,18,19,20 (Tranke). Reihenfolge: Shiny, IV, Legendary,
      Static. Nur zum Ausprobieren ohne Cheat.
  --ground-charms P: Jeder Ball auf dem Boden (213 Stueck, Skriptdatei a/0/5/6 Nr. 1241) wird mit P Prozent
      Chance zu einem zufaelligen Charm (Meldung "... gefunden" passt automatisch). --seed N legt den
      Zufall fest (sonst wird er zufaellig gewaehlt und angezeigt).
  --quiet-dialog: Ersetzt jeden gesprochenen Text (Dialoge mit "Warte auf Taste"-Steuercode) durch
      einen einzelnen Punkt. Alles geht schneller; Menues, Itemnamen und Kampftexte bleiben.
Die Original-ROM wird nur gelesen. Geaendert werden:
  1. Text-Archiv a/0/0/2 (Eintraege 63, 64, 481, 482; Zeilen 179-182): Namen/Beschreibungen.
  2. Overlay 36 (Kampf): drei Einhaengestellen in der Funktion, die wilde Pokemon erzeugt.
  3. ARM9 (wird dafuer entpackt gespeichert): Zusatzfunktionen in einem ungenutzten Block.
Finden: Wilde Pokemon tragen mit Chance 1 zu N einen zufaelligen Charm (Fangen, dann Item nehmen).
Wirkung: Beim naechsten wilden Pokemon wird je 1 Charm aus dem Beutel verbraucht:
  Shiny Charm (179)    -> das Pokemon ist (fast sicher) shiny
  100% IV Charm (180)  -> alle IVs 31
  Legendary Charm (181)-> zufaelliges legendaeres Pokemon (Level wie die Begegnung)
  Static Charm (182)   -> zufaelliges Pokemon mit 600+ Basiswerten (Level wie die Begegnung)
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

import hashlib  # noqa: E402
import random  # noqa: E402

import charm_code as CC  # noqa: E402

OV_ID = 36
OV_RAM_ADDR = 0x0217F600
OV_RAM_SIZE = 0x561A0
ARM9_BASE = 0x02004000
DEFAULT_ITEMS = (179, 180, 181, 182)  # Shiny, IV, Legendary, Static
ITEM_IDS = DEFAULT_ITEMS
NITRO_MAGIC = b"\x21\x06\xc0\xde"  # Modulparameter-Kennung im ARM9

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
    ov = bytearray(ov)
    for addr, orig, new in CC.OV_SITES:
        off = addr - OV_RAM_ADDR
        if bytes(ov[off:off + len(orig)]) != orig:
            sys.exit("Eine Code-Stelle im Overlay 36 passt nicht zum erwarteten Original. "
                     "Diese ROM-Version (oder schon gepatcht?) wird nicht unterstuetzt. Nichts geschrieben.")
        ov[off:off + len(new)] = new
    return bytes(ov)


FIND_RATE = CC.FIND_RATE_DEFAULT  # wilde Pokemon tragen mit Chance 1 zu N einen Charm


def cave_blob(item_ids, find_rate=None):
    """Zusatzcode mit den gewuenschten Item-IDs (Standard 179-182) und Fundchance 1 zu N."""
    find_rate = FIND_RATE if find_rate is None else find_rate
    blob = bytearray(CC.CAVE_BLOB)
    o = CC.FIND_RATE_OFFSET
    assert blob[o] == CC.FIND_RATE_DEFAULT and blob[o + 1] == 0x20, "Zusatzcode unerwartet aufgebaut"
    blob[o] = find_rate
    for off, default, new in zip(CC.ITEM_ID_OFFSETS, DEFAULT_ITEMS, item_ids):
        assert blob[off] == default and blob[off + 1] == 0x21, "Zusatzcode unerwartet aufgebaut"
        blob[off] = new
    return bytes(blob)


def module_params_offset(a9):
    idx = a9.find(NITRO_MAGIC)
    if idx < 0x1C:
        sys.exit("ARM9-Modulparameter nicht gefunden. Diese ROM-Version passt nicht.")
    return idx - 0x1C


def read_arm9(rom):
    """ARM9 aus der ROM; ist er komprimiert (Feld compressed_static_end != 0), wird er entpackt."""
    off, size = u32(rom, 0x20), u32(rom, 0x2C)
    raw = bytes(rom[off:off + size])
    mp = raw[:0x4000].find(NITRO_MAGIC)  # die ersten 0x4000 Bytes sind nie komprimiert
    if mp >= 0x1C and u32(raw, mp - 0x1C + 0x14) == 0:
        return raw
    return blz_decompress(raw)


def patch_arm9(rom, item_ids, find_rate=None):
    """Gibt den entpackten, gepatchten ARM9 zurueck."""
    a9 = bytearray(read_arm9(rom))
    cave = CC.CAVE_ADDR - ARM9_BASE
    n = len(CC.CAVE_BLOB)
    if hashlib.sha1(bytes(a9[cave:cave + n])).hexdigest() != CC.CAVE_ORIG_SHA1:
        sys.exit("Der Platz fuer den Zusatzcode im ARM9 passt nicht zum erwarteten Original. "
                 "Diese ROM-Version (oder schon gepatcht?) wird nicht unterstuetzt. Nichts geschrieben.")
    a9[cave:cave + n] = cave_blob(item_ids, find_rate)
    cse = module_params_offset(a9) + 0x14  # "compressed_static_end": 0 = nicht komprimiert
    struct.pack_into("<I", a9, cse, 0)
    return bytes(a9)


def find_narc(rom, path):
    paths = parse_fnt(rom, u32(rom, 0x40), u32(rom, 0x44))
    fid = next((i for i, p in paths.items() if p == path), None)
    if fid is None:
        sys.exit(f"{path} nicht gefunden")
    s, e = struct.unpack_from("<II", rom, u32(rom, 0x48) + fid * 8)
    return fid, s, e


def find_text_narc(rom):
    return find_narc(rom, TEXT_NARC)


WAIT_TAG = [0xF000, 0xBE01, 0x0000]  # "Warte auf Taste" (Seitenwechsel im Dialog)
QUIET_WORDS = [ord("."), 0xF000, 0xBE01, 0x0000, 0xFFFF]
DIALOG_NARCS = ("a/0/0/2", "a/0/0/3")
GROUND_NARC = "a/0/5/6"
GROUND_ENTRY = 1241  # Skriptdatei mit den Ball-Skripten (je 30 Bytes, gleicher Aufbau)
GROUND_SCRIPT_LEN = 30
CHARM_ITEMS = (179, 180, 181, 182)
QUIET = False


def has_wait_tag(words):
    return any(words[i:i + 3] == WAIT_TAG for i in range(len(words) - 2))


def quiet_entry(data):
    """Ersetzt alle Dialogzeilen eines Text-Archivs durch '.' + Warte-Code. Gibt (Daten, Anzahl) zurueck."""
    if len(data) < 0x14 or u16(data, 0) != 1 or u16(data, 2) == 0:
        return data, 0
    header, lines = parse_text_entry(data)
    count = 0
    for i, line in enumerate(lines):
        words = crypt_words(raw_to_words(line[0]), i)
        if has_wait_tag(words):
            line[0] = words_to_raw(crypt_words(QUIET_WORDS, i))
            count += 1
    return (build_text_entry(header, lines) if count else data), count


def quiet_entries(entries):
    out, total = [], 0
    for d in entries:
        nd, c = quiet_entry(d)
        out.append(nd)
        total += c
    return out, total


def ground_scripts(data):
    """Prueft die Ball-Skript-Datei und gibt die Startpositionen der Skripte zurueck."""
    if (len(data) - 2) % (4 + GROUND_SCRIPT_LEN):
        sys.exit("Ball-Skript-Datei hat eine unerwartete Groesse. Diese ROM-Version wird nicht unterstuetzt.")
    n = (len(data) - 2) // (4 + GROUND_SCRIPT_LEN)
    starts = []
    for i in range(n):
        off = u32(data, 4 * i)
        st = 4 * i + 4 + off
        sc = data[st:st + GROUND_SCRIPT_LEN]
        ok = (len(sc) == GROUND_SCRIPT_LEN and sc[0:2] == b"\x2e\x00" and sc[2:6] == b"\x2a\x00\x00\x80"
              and sc[8:12] == b"\x2a\x00\x01\x80" and sc[14:18] == b"\x2a\x00\x02\x80"
              and u16(sc, 12) == 1 and u16(sc, 22) == 2811)
        if not ok:
            sys.exit(f"Ball-Skript {i} hat einen unerwarteten Aufbau. Diese ROM-Version wird nicht unterstuetzt.")
        starts.append(st)
    return starts


def patch_ground(entry, percent, seed):
    """Macht jeden Ball mit 'percent' Prozent Chance zu einem zufaelligen Charm. Gibt (Daten, Liste) zurueck."""
    rng = random.Random(seed)
    data = bytearray(entry)
    changed = []
    for i, st in enumerate(ground_scripts(entry)):
        if rng.random() * 100 < percent:
            new = rng.choice(CHARM_ITEMS)
            changed.append((i, u16(entry, st + 6), new))
            struct.pack_into("<H", data, st + 6, new)
    return bytes(data), changed


def expected_text(rom, quiet):
    """Gibt {Pfad: (fid, Original-Eintraege, erwartete neue Eintraege, BTNF, Anzahl ersetzter Zeilen)}."""
    res = {}
    paths = DIALOG_NARCS if quiet else (TEXT_NARC,)
    for path in paths:
        fid, s, e = find_narc(rom, path)
        entries = read_narc(rom, s, e)
        new, cnt = quiet_entries(entries) if quiet else (list(entries), 0)
        res[path] = (fid, entries, new, parse_narc_blocks(rom, s), cnt)
    return res


def charm_patch(baseline):
    """Namen und Beschreibungen der vier Charms in die Eintraege schreiben (Kopie)."""
    out = list(baseline)
    names = {ln: v[0] for ln, v in CHARMS.items()}
    descs = {ln: v[1] for ln, v in CHARMS.items()}
    for idx in NAME_ENTRIES:
        out[idx] = patch_entry(baseline[idx], idx, names)
    out[DESC_ENTRY] = patch_entry(baseline[DESC_ENTRY], DESC_ENTRY, descs)
    return out


def patch_rom(rom, item_ids=DEFAULT_ITEMS, quiet=False, ground=None):
    texts = expected_text(rom, quiet)
    fid, entries, baseline, btnf, _ = texts[TEXT_NARC]
    new_entries = charm_patch(baseline)
    blobs = [("text", fid, build_narc(new_entries, btnf))]
    if quiet:
        f3, _, n3, b3, _ = texts["a/0/0/3"]
        blobs.append(("text", f3, build_narc(n3, b3)))
    if ground:
        gf, gs, ge = find_narc(rom, GROUND_NARC)
        gentries = read_narc(rom, gs, ge)
        new_g, changed = patch_ground(gentries[GROUND_ENTRY], *ground)
        gnew = list(gentries)
        gnew[GROUND_ENTRY] = new_g
        texts["ground"] = (gf, gentries, gnew, parse_narc_blocks(rom, gs), changed)
        blobs.append(("text", gf, build_narc(gnew, texts["ground"][3])))
    ov_new = patch_overlay(rom)
    a9_new = patch_arm9(rom, item_ids)

    out = bytearray(rom)
    ov_off = u32(rom, 0x50) + OV_ID * 32
    fat = u32(rom, 0x48)
    pos = max(len(rom), u32(rom, 0x80))
    for kind, file_id, blob in blobs + [("ov", None, ov_new), ("arm9", None, a9_new)]:
        pos += -pos % 0x200
        out += b"\0" * (pos - len(out))
        out += blob
        if kind == "text":
            struct.pack_into("<II", out, fat + file_id * 8, pos, pos + len(blob))
        elif kind == "ov":  # Overlay 36 unkomprimiert: FAT und Overlay-Tabelle anpassen
            struct.pack_into("<II", out, fat + u32(rom, ov_off + 24) * 8, pos, pos + len(blob))
            struct.pack_into("<I", out, ov_off + 28, 0x02000000)
        else:  # ARM9 unkomprimiert: Kopf zeigt auf die neue Position und Groesse
            struct.pack_into("<I", out, 0x20, pos)
            struct.pack_into("<I", out, 0x2C, len(blob))
        pos += len(blob)
    struct.pack_into("<I", out, 0x80, pos)
    # Secure-Area-CRC im Kopf (0x6C) nachziehen, falls sie vorher zu den ersten 0x4000 ARM9-Bytes passte
    a9_old = read_arm9(rom)
    if u16(rom, 0x6C) == crc16(a9_old[:0x4000]):
        struct.pack_into("<H", out, 0x6C, crc16(a9_new[:0x4000]))
    struct.pack_into("<H", out, 0x15E, crc16(bytes(out[:0x15E])))
    return bytes(out), entries, new_entries, texts


def diff_ranges(a, b):
    """Liste der (Start, Ende) abweichender Bereiche zweier gleich langer Byte-Folgen."""
    assert len(a) == len(b)
    out, i = [], 0
    while i < len(a):
        if a[i] != b[i]:
            j = i
            while j < len(a) and a[j] != b[j]:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def verify(old_rom, new_rom, texts, item_ids, quiet=False):
    fid, s, e = find_text_narc(new_rom)
    got = read_narc(new_rom, s, e)
    _, old_entries, baseline, _, _ = texts[TEXT_NARC]
    new_entries = charm_patch(baseline)
    assert len(got) == len(new_entries), "Eintragszahl falsch"
    changed = set(NAME_ENTRIES) | {DESC_ENTRY}
    for i, (g, n, b0) in enumerate(zip(got, new_entries, baseline)):
        assert g == n, f"Eintrag {i} nach dem Schreiben anders"
        if i not in changed:
            assert g == b0, f"Eintrag {i} ungewollt veraendert"
    if "ground" in texts:
        gf, gold, gnew, _, changed = texts["ground"]
        gs, ge = struct.unpack_from("<II", new_rom, u32(new_rom, 0x48) + gf * 8)
        got_g = read_narc(new_rom, gs, ge)
        assert got_g == gnew, "Ball-Skripte nach dem Schreiben anders"
        assert [i for i, (a, b) in enumerate(zip(gold, gnew)) if a != b] in ([], [GROUND_ENTRY]), \
            "Ausser Datei 1241 wurde etwas veraendert"
        for i, old_item, new_item in changed:
            assert new_item in CHARM_ITEMS
    if quiet:
        f3, s3, e3 = find_narc(new_rom, "a/0/0/3")
        got3 = read_narc(new_rom, s3, e3)
        assert got3 == texts["a/0/0/3"][2], "Dialog-Archiv a/0/0/3 stimmt nicht"
        assert sum(t[4] for k, t in texts.items() if k != "ground") > 0, "Keine Dialogzeilen gefunden"
    assert u16(new_rom, 0x15E) == crc16(new_rom[:0x15E]), "Header-CRC falsch"
    # Overlay 36: nur die Einhaengestellen duerfen abweichen
    _, _, ov_old = read_overlay(old_rom, OV_ID)
    _, _, ov_new = read_overlay(new_rom, OV_ID)
    assert len(ov_new) == OV_RAM_SIZE
    sites = [(a - OV_RAM_ADDR, a - OV_RAM_ADDR + len(n)) for a, _, n in CC.OV_SITES]
    for lo, hi in diff_ranges(ov_old, ov_new):
        assert any(s0 <= lo and hi <= s1 for s0, s1 in sites), "Overlay ausserhalb der Stellen veraendert"
    for a, _, n in CC.OV_SITES:
        assert ov_new[a - OV_RAM_ADDR:a - OV_RAM_ADDR + len(n)] == n, "Overlay-Stelle falsch"
    # ARM9: nur Zusatzcode und das Kompressions-Feld duerfen abweichen, erste 0x4000 Bytes gleich
    a9_old, a9_new = read_arm9(old_rom), read_arm9(new_rom)
    cave = CC.CAVE_ADDR - ARM9_BASE
    cse = module_params_offset(a9_new) + 0x14
    # In den ersten 0x4000 Bytes (Secure Area) darf nur das Kompressions-Feld abweichen
    assert diff_ranges(a9_old[:0x4000], a9_new[:0x4000]) == [(cse, cse + 4)], "Secure Area veraendert"
    if u16(old_rom, 0x6C) == crc16(a9_old[:0x4000]):
        assert u16(new_rom, 0x6C) == crc16(a9_new[:0x4000]), "Secure-Area-CRC nicht nachgezogen"
    allowed = [(cave, cave + len(CC.CAVE_BLOB)), (cse, cse + 4)]
    for lo, hi in diff_ranges(a9_old, a9_new):
        assert any(s0 <= lo and hi <= s1 for s0, s1 in allowed), "ARM9 ausserhalb der Stellen veraendert"
    assert a9_new[cave:cave + len(CC.CAVE_BLOB)] == cave_blob(item_ids), "Zusatzcode falsch"
    assert u32(a9_new, cse) == 0, "ARM9 noch als komprimiert markiert"
    assert u32(new_rom, 0x2C) == len(a9_new), "ARM9-Groesse im Kopf falsch"


def main(src, dst, item_ids=DEFAULT_ITEMS, quiet=False, ground=None):
    if os.path.abspath(src) == os.path.abspath(dst):
        sys.exit("Ziel darf nicht die Original-ROM sein.")
    with open(src, "rb") as f:
        rom = f.read()
    new_rom, old_entries, new_entries, texts = patch_rom(rom, item_ids, quiet, ground)
    verify(rom, new_rom, texts, item_ids, quiet)
    with open(dst, "xb") as f:
        f.write(new_rom)
    print(f"Fertig: {dst} ({len(new_rom)} Bytes). Original unveraendert.")
    names = ("Shiny Charm", "100% IV Charm", "Legendary Charm", "Static Charm")
    for n, i in zip(names, item_ids):
        print(f"  {n}: Item {i}")
    print("Wirkung: beim naechsten wilden Pokemon wird je 1 Charm aus dem Beutel verbraucht.")
    print(f"Finden: wilde Pokemon tragen mit Chance 1 zu {FIND_RATE} einen zufaelligen Charm.")
    if quiet:
        n = sum(t[4] for k, t in texts.items() if k != "ground")
        print(f"Dialoge: {n} gesprochene Textzeilen durch '.' ersetzt.")
    if ground:
        ch = texts["ground"][4]
        print(f"Boden-Charms: {len(ch)} von 213 Baellen sind jetzt Charms ({ground[0]} %, Zufall-Startwert {ground[1]}).")


if __name__ == "__main__":
    args = sys.argv[1:]
    items = DEFAULT_ITEMS
    if "--test-items" in args:
        k = args.index("--test-items")
        try:
            items = tuple(int(x) for x in args[k + 1].split(","))
        except (IndexError, ValueError):
            sys.exit(__doc__)
        if len(items) != 4 or not all(1 <= x <= 255 for x in items) or len(set(items)) != 4:
            sys.exit("--test-items: genau vier verschiedene IDs zwischen 1 und 255, z. B. 17,18,19,20")
        del args[k:k + 2]
    ground = None
    if "--ground-charms" in args:
        k = args.index("--ground-charms")
        try:
            pct = float(args[k + 1])
        except (IndexError, ValueError):
            sys.exit(__doc__)
        if not 0 < pct <= 100:
            sys.exit("--ground-charms: Prozent zwischen 1 und 100 (z. B. 20).")
        del args[k:k + 2]
        seed = random.SystemRandom().randrange(1, 10**6)
        if "--seed" in args:
            k = args.index("--seed")
            try:
                seed = int(args[k + 1])
            except (IndexError, ValueError):
                sys.exit(__doc__)
            del args[k:k + 2]
        ground = (pct, seed)
    quiet = "--quiet-dialog" in args
    if quiet:
        args.remove("--quiet-dialog")
    if "--find-rate" in args:
        k = args.index("--find-rate")
        try:
            FIND_RATE = int(args[k + 1])
        except (IndexError, ValueError):
            sys.exit(__doc__)
        if not 1 <= FIND_RATE <= 255:
            sys.exit("--find-rate: Zahl zwischen 1 und 255 (1 = jedes wilde Pokemon traegt einen Charm).")
        del args[k:k + 2]
    if len(args) != 2:
        sys.exit(__doc__)
    ITEM_IDS = items
    main(args[0], args[1], items, quiet, ground)
