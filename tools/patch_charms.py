#!/usr/bin/env python3
"""Charm-Mod fuer Pokemon Schwarz 2: die 17 Edelsteine werden zu Charms. Schreibt eine NEUE ROM.

Aufruf:  python tools/patch_charms.py "original.nds" "neue_rom.nds" [Optionen]
Die 17 Edelsteine (Gems, Item 548-564) werden zu Charms: 8 Shiny Charms, 4 100% IV Charms, 3 Legendary
Charms, 2 Static Charms. Jeder Edelstein liegt in den versteckten Items schon einmal in der Spielwelt.
Optionen:
  --find-rate N: Wilde Pokemon tragen mit Chance 1 zu N einen zufaelligen Edelstein-Charm (Standard 20).
  --test-items A,B,C,D: Testvariante: Der Effekt haengt zusaetzlich nur an den Items A (Shiny), B (IV),
      C (Legendary), D (Static), IDs 1-255, z. B. 17,26,25,24 (Traenke).
  --ground-charms P: Jeder sichtbare Ball auf dem Boden (400 Stueck, Skriptdatei a/0/5/6 Nr. 1240) wird mit
      P Prozent Chance zu einem zufaelligen Edelstein-Charm (TMs/HMs und Edelsteine bleiben).
  --hidden-charms P: Dasselbe fuer versteckte Items (213 Stueck, Nr. 1241).
  --seed N legt den Zufall fest (sonst wird er zufaellig gewaehlt und angezeigt).
  --random-wild: Alle wilden Begegnungen (a/1/2/7) werden zufaellig umbesetzt: jede vorkommende Art wird
      einer anderen zufaelligen Art zugeordnet, Level und Raten bleiben.
  --random-starters: Die drei Starter werden zufaellige Arten (Skript 854 + Schrei-Tabelle Overlay 316).
      Das Auswahlbild zeigt weiter die Original-Pokemon! Fuer saubere Starter besser den ZX-Randomizer nehmen.
  --allow-legendary: Beim Zufall (Wild/Starter) auch legendaere/mythische Pokemon zulassen (sonst nicht).
  --quiet-dialog: Ersetzt jeden gesprochenen Text (Dialoge mit "Warte auf Taste"-Steuercode) durch
      einen einzelnen Punkt. Alles geht schneller; Menues, Itemnamen und Kampftexte bleiben.
Die Original-ROM wird nur gelesen. Geaendert werden:
  1. Text-Archiv a/0/0/2 (Eintraege 63, 64, 481, 482; Zeilen 548-564 = Edelsteine): Namen/Beschreibungen.
  2. Overlay 36 (Kampf): drei Einhaengestellen in der Funktion, die wilde Pokemon erzeugt.
  3. ARM9 (wird dafuer entpackt gespeichert): Zusatzfunktionen in einem ungenutzten Block.
Finden: Die 17 Edelsteine liegen als versteckte Items in der Welt; wilde Pokemon tragen mit Chance 1 zu N
  einen zufaelligen Edelstein-Charm (Fangen, dann Item nehmen).
Wirkung: Beim naechsten wilden Pokemon wird jeder Charm im Beutel (je 1 Stueck) verbraucht:
  Shiny Charm (8 Items)     -> das Pokemon ist (fast sicher) shiny
  100% IV Charm (4 Items)   -> alle IVs 31
  Legendary Charm (3 Items) -> zufaelliges legendaeres Pokemon (Level wie die Begegnung)
  Static Charm (2 Items)    -> zufaelliges Pokemon mit 600+ Basiswerten (Level wie die Begegnung)
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
import randomizer as R  # noqa: E402

OV_ID = 36
OV_RAM_ADDR = 0x0217F600
OV_RAM_SIZE = 0x561A0
ARM9_BASE = 0x02004000
NITRO_MAGIC = b"\x21\x06\xc0\xde"  # Modulparameter-Kennung im ARM9

# Die 17 Edelsteine (Gems, Item 548..564) sind die Charms. Gruppen: (Bit, Name, Beschreibung)
GROUP_TEXT = {
    0: ("Shiny Charm", "Makes the next wild Pokémon you\nmeet shiny. Used up after one\nencounter."),
    1: ("100% IV Charm", "Makes the next wild Pokémon you\nmeet have perfect IVs. Used up\nafter one encounter."),
    2: ("Legendary Charm", "Makes the next wild encounter a\nlegendary Pokémon. Used up after\none encounter."),
    3: ("Static Charm", "Makes the next wild Pokémon have\n600+ base stats, like a static\nencounter. Used up after use."),
}
GROUPS = tuple((bit, tuple(ids)) for bit, ids in CC.GROUPS)
CHARM_ITEMS = tuple(i for _, ids in GROUPS for i in ids)  # 17 Edelsteine
CHARMS = {}  # Zeile (= Item-Nummer): (Name, Beschreibung)
for _bit, _ids in GROUPS:
    for _i in _ids:
        CHARMS[_i] = GROUP_TEXT[_bit]
GEM_WORDS = ("gem", "joia", "jóia", "jewel")  # Namenspruefung: die Items muessen Edelsteine sein


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


def cave_blob(test_items=None, find_rate=None):
    """Zusatzcode. Standard: die 17 Edelsteine. Mit test_items=(A,B,C,D): je Gruppe nur dieses eine Item."""
    find_rate = FIND_RATE if find_rate is None else find_rate
    blob = bytearray(CC.CAVE_BLOB)
    o = CC.FIND_RATE_OFFSET
    assert blob[o] == CC.FIND_RATE_DEFAULT and blob[o + 1] == 0x20, "Zusatzcode unerwartet aufgebaut"
    blob[o] = find_rate
    k = 0
    for bit, ids in GROUPS:
        for n, gem in enumerate(ids):
            off = CC.ITEM_LOAD_OFFSETS[k]
            k += 1
            expect = bytes([gem >> 8, 0x21, 0x09, 0x02, gem & 255, 0x31])
            assert bytes(blob[off:off + 6]) == expect, "Zusatzcode unerwartet aufgebaut"
            if test_items:
                new = test_items[bit] if n == 0 else 0xFFFF  # 0xFFFF = kein Item
                blob[off:off + 6] = bytes([new >> 8, 0x21, 0x09, 0x02, new & 255, 0x31])
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


def patch_arm9(rom, test_items=None, find_rate=None):
    """Gibt den entpackten, gepatchten ARM9 zurueck."""
    a9 = bytearray(read_arm9(rom))
    cave = CC.CAVE_ADDR - ARM9_BASE
    n = len(CC.CAVE_BLOB)
    if hashlib.sha1(bytes(a9[cave:cave + n])).hexdigest() != CC.CAVE_ORIG_SHA1:
        sys.exit("Der Platz fuer den Zusatzcode im ARM9 passt nicht zum erwarteten Original. "
                 "Diese ROM-Version (oder schon gepatcht?) wird nicht unterstuetzt. Nichts geschrieben.")
    a9[cave:cave + n] = cave_blob(test_items, find_rate)
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
WILD_NARC = "a/1/2/7"
GROUND_NARC = "a/0/5/6"
BALL_ENTRY = 1240    # sichtbare Baelle auf dem Boden (401 Skripte zu je 26 Bytes)
HIDDEN_ENTRY = 1241  # versteckte Items (213 Skripte zu je 30 Bytes)
HIDDEN_SCRIPT_LEN = 30
BALL_SCRIPT_LEN = 26
TM_RANGE = range(328, 428)  # TMs/HMs: werden standardmaessig nicht ersetzt
STARTER_SCRIPT = 854
STARTER_OFFSETS = ((0x58B, 0x590, 0x595), (0x5C0, 0x5C5, 0x5CA), (0x5E2, 0x5E7, 0x5EC))
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


def patch_starters(rom, picks):
    """Gibt das gepatchte Overlay 316 (Starter-Tabelle) zurueck."""
    ov_off, fid, ov = read_overlay(rom, R.STARTER_OV_ID)
    if u32(rom, ov_off + 4) != R.STARTER_OV_RAM or len(ov) != R.STARTER_OV_SIZE:
        sys.exit("Overlay 316 hat nicht die erwartete Groesse/Adresse. Diese ROM-Version passt nicht.")
    off = R.STARTER_TABLE_ADDR - R.STARTER_OV_RAM
    if struct.unpack_from("<6H", ov, off) != R.STARTER_ORIGINAL:
        sys.exit("Die Starter-Tabelle passt nicht zum erwarteten Original. Diese ROM-Version "
                 "(oder schon gepatcht?) wird nicht unterstuetzt. Nichts geschrieben.")
    ov = bytearray(ov)
    struct.pack_into("<3H", ov, off, *picks)
    return bytes(ov)


def hidden_positions(data):
    """Prueft die Datei der versteckten Items und gibt die Positionen der Item-Nummern zurueck."""
    if (len(data) - 2) % (4 + HIDDEN_SCRIPT_LEN):
        sys.exit("Skriptdatei der versteckten Items hat eine unerwartete Groesse. ROM-Version nicht unterstuetzt.")
    n = (len(data) - 2) // (4 + HIDDEN_SCRIPT_LEN)
    pos = []
    for i in range(n):
        st = 4 * i + 4 + u32(data, 4 * i)
        sc = data[st:st + HIDDEN_SCRIPT_LEN]
        ok = (len(sc) == HIDDEN_SCRIPT_LEN and sc[0:2] == b"\x2e\x00" and sc[2:6] == b"\x2a\x00\x00\x80"
              and sc[8:12] == b"\x2a\x00\x01\x80" and sc[14:18] == b"\x2a\x00\x02\x80"
              and u16(sc, 12) == 1 and u16(sc, 22) == 2811)
        if not ok:
            sys.exit(f"Skript {i} der versteckten Items hat einen unerwarteten Aufbau. ROM-Version nicht unterstuetzt.")
        pos.append(st + 6)
    return pos


def ball_positions(data):
    """Prueft die Ball-Skriptdatei (ein Skript mit anderem Aufbau am Ende ist erlaubt)."""
    m = next((p for p in range(0, len(data) - 1, 4) if u16(data, p) == 0xFD13), None)
    if m is None:
        sys.exit("Ball-Skriptdatei hat kein Kennzeichen. Diese ROM-Version wird nicht unterstuetzt.")
    n = m // 4
    pos, bad = [], 0
    for i in range(n):
        st = 4 * i + 4 + u32(data, 4 * i)
        sc = data[st:st + BALL_SCRIPT_LEN]
        ok = (len(sc) == BALL_SCRIPT_LEN and sc[0:2] == b"\x2e\x00" and sc[2:6] == b"\x28\x00\x0c\x80"
              and sc[8:12] == b"\x28\x00\x0d\x80" and sc[14:16] == b"\x04\x00")
        if ok:
            pos.append(st + 6)
        else:
            bad += 1
    if bad > 1 or len(pos) < 300:
        sys.exit("Ball-Skripte haben einen unerwarteten Aufbau. Diese ROM-Version wird nicht unterstuetzt.")
    return pos


def convert_items(entry, positions, percent, rng):
    """Macht jeden Fund mit 'percent' Prozent Chance zu einem zufaelligen Charm (TMs/HMs bleiben)."""
    data = bytearray(entry)
    changed = []
    for i, p in enumerate(positions):
        old = u16(entry, p)
        if old in TM_RANGE or old in CHARM_ITEMS:
            continue
        if rng.random() * 100 < percent:
            new = rng.choice(CHARM_ITEMS)
            changed.append((i, old, new))
            struct.pack_into("<H", data, p, new)
    return bytes(data), changed


def patch_starter_script(entry, picks):
    """Setzt die drei Starter im Skript 854 (je dreimal pro Starter)."""
    data = bytearray(entry)
    for offs, orig, new in zip(STARTER_OFFSETS, R.STARTER_ORIGINAL[:3], picks):
        for o in offs:
            if u16(entry, o) != orig:
                sys.exit("Starter-Skript passt nicht zum erwarteten Original. ROM-Version nicht unterstuetzt.")
            struct.pack_into("<H", data, o, new)
    return bytes(data)


def patch_scripts(rom, ground, picks, seed):
    """Aendert im Skript-Archiv: Baelle, versteckte Items, Starter. Gibt (fid, alt, neu, BTNF, Info) zurueck."""
    fid, s, e = find_narc(rom, GROUND_NARC)
    old = read_narc(rom, s, e)
    new = list(old)
    info = {"balls": [], "hidden": [], "starters": picks}
    if ground and ground.get("balls"):
        new[BALL_ENTRY], info["balls"] = convert_items(old[BALL_ENTRY], ball_positions(old[BALL_ENTRY]),
                                                       ground["balls"], random.Random(seed * 7 + 3))
    if ground and ground.get("hidden"):
        new[HIDDEN_ENTRY], info["hidden"] = convert_items(old[HIDDEN_ENTRY], hidden_positions(old[HIDDEN_ENTRY]),
                                                          ground["hidden"], random.Random(seed * 7 + 4))
    if picks:
        new[STARTER_SCRIPT] = patch_starter_script(old[STARTER_SCRIPT], picks)
    return fid, old, new, parse_narc_blocks(rom, s), info


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


def check_gem_names(baseline):
    """Bricht ab, wenn die Items 548..564 keine Edelsteine sind (Namenspruefung, Eintrag 64)."""
    header, lines = parse_text_entry(baseline[64])
    bad = []
    for gem in CHARM_ITEMS:
        words = crypt_words(raw_to_words(lines[gem][0]), gem)
        name = "".join(chr(w) for w in words if 32 <= w < 0xF000).lower()
        if not any(w in name for w in GEM_WORDS):
            bad.append((gem, name))
    if bad:
        print("Die Items 548..564 sind in dieser ROM keine Edelsteine (oder schon umbenannt):")
        for gem, name in bad:
            print(f"  {gem}: {name}")
        sys.exit("Nichts geschrieben. Bitte diese Liste an Claude schicken.")


def charm_patch(baseline):
    """Namen und Beschreibungen der Charms in die Eintraege schreiben (Kopie)."""
    check_gem_names(baseline)
    out = list(baseline)
    names = {ln: v[0] for ln, v in CHARMS.items()}
    descs = {ln: v[1] for ln, v in CHARMS.items()}
    for idx in NAME_ENTRIES:
        out[idx] = patch_entry(baseline[idx], idx, names)
    out[DESC_ENTRY] = patch_entry(baseline[DESC_ENTRY], DESC_ENTRY, descs)
    return out


def patch_rom(rom, test_items=None, quiet=False, ground=None, rand=None):
    texts = expected_text(rom, quiet)
    fid, entries, baseline, btnf, _ = texts[TEXT_NARC]
    new_entries = charm_patch(baseline)
    blobs = [("text", fid, build_narc(new_entries, btnf))]
    if quiet:
        f3, _, n3, b3, _ = texts["a/0/0/3"]
        blobs.append(("text", f3, build_narc(n3, b3)))
    extra_ovs = []
    if rand and rand["wild"]:
        wf, ws, we = find_narc(rom, WILD_NARC)
        wentries = read_narc(rom, ws, we)
        rng = random.Random(rand["seed"] * 7 + 1)
        pool = R.species_pool(rand["legendary"])
        mapping = R.make_mapping(R.species_in_wild(wentries), pool, rng)
        wnew = R.randomize_wild(wentries, mapping)
        texts["wild"] = (wf, wentries, wnew, parse_narc_blocks(rom, ws), mapping)
        blobs.append(("text", wf, build_narc(wnew, texts["wild"][3])))
    picks = None
    if rand and rand["starters"]:
        rng = random.Random(rand["seed"] * 7 + 2)
        picks = R.pick_starters(R.species_pool(rand["legendary"]), rng)
        texts["starters"] = picks
        extra_ovs.append(("ov", R.STARTER_OV_ID, patch_starters(rom, picks)))
    if ground or picks:
        sf, sold, snew, sbtnf, sinfo = patch_scripts(rom, ground, picks, (ground or rand or {"seed": 1})["seed"])
        texts["scripts"] = (sf, sold, snew, sbtnf, sinfo)
        blobs.append(("text", sf, build_narc(snew, sbtnf)))
    ov_new = patch_overlay(rom)
    a9_new = patch_arm9(rom, test_items)

    out = bytearray(rom)
    ov_off = u32(rom, 0x50) + OV_ID * 32
    fat = u32(rom, 0x48)
    pos = max(len(rom), u32(rom, 0x80))
    for kind, file_id, blob in blobs + [("ov", OV_ID, ov_new)] + extra_ovs + [("arm9", None, a9_new)]:
        pos += -pos % 0x200
        out += b"\0" * (pos - len(out))
        out += blob
        if kind == "text":
            struct.pack_into("<II", out, fat + file_id * 8, pos, pos + len(blob))
        elif kind == "ov":  # Overlay 36 unkomprimiert: FAT und Overlay-Tabelle anpassen
            o_off = u32(rom, 0x50) + file_id * 32
            struct.pack_into("<II", out, fat + u32(rom, o_off + 24) * 8, pos, pos + len(blob))
            struct.pack_into("<I", out, o_off + 28, 0x02000000)
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


def verify(old_rom, new_rom, texts, test_items, quiet=False):
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
    if "wild" in texts:
        wf, wold, wnew, _, _ = texts["wild"]
        ws, we = struct.unpack_from("<II", new_rom, u32(new_rom, 0x48) + wf * 8)
        assert read_narc(new_rom, ws, we) == wnew, "Begegnungen nach dem Schreiben anders"
    if "starters" in texts:
        _, _, sov_old = read_overlay(old_rom, R.STARTER_OV_ID)
        _, _, sov_new = read_overlay(new_rom, R.STARTER_OV_ID)
        off = R.STARTER_TABLE_ADDR - R.STARTER_OV_RAM
        assert struct.unpack_from("<3H", sov_new, off) == tuple(texts["starters"]), "Starter falsch"
        for lo, hi in diff_ranges(sov_old, sov_new):
            assert off <= lo and hi <= off + 6, "Overlay 316 ausserhalb der Tabelle veraendert"
    if "scripts" in texts:
        sf, sold, snew, _, sinfo = texts["scripts"]
        ss, se = struct.unpack_from("<II", new_rom, u32(new_rom, 0x48) + sf * 8)
        got_s = read_narc(new_rom, ss, se)
        assert got_s == snew, "Skripte nach dem Schreiben anders"
        allowed = {BALL_ENTRY, HIDDEN_ENTRY, STARTER_SCRIPT}
        diff_idx = {i for i, (a, b) in enumerate(zip(sold, snew)) if a != b}
        assert diff_idx <= allowed, "Unerlaubte Skriptdatei veraendert"
        for lst in (sinfo["balls"], sinfo["hidden"]):
            for _, old_item, new_item in lst:
                assert new_item in CHARM_ITEMS and old_item not in TM_RANGE and old_item not in CHARM_ITEMS
        if sinfo["starters"]:
            for offs, new in zip(STARTER_OFFSETS, sinfo["starters"]):
                for o in offs:
                    assert u16(got_s[STARTER_SCRIPT], o) == new, "Starter im Skript falsch"
    if quiet:
        f3, s3, e3 = find_narc(new_rom, "a/0/0/3")
        got3 = read_narc(new_rom, s3, e3)
        assert got3 == texts["a/0/0/3"][2], "Dialog-Archiv a/0/0/3 stimmt nicht"
        assert sum(texts[k][4] for k in DIALOG_NARCS if k in texts) > 0, "Keine Dialogzeilen gefunden"
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
    # In den ersten 0x4000 Bytes (Secure Area) darf hoechstens das Kompressions-Feld abweichen
    # (War der ARM9 schon entpackt, z. B. nach dem ZX-Randomizer, steht das Feld schon auf 0: keine Abweichung.)
    sec = diff_ranges(a9_old[:0x4000], a9_new[:0x4000])
    if any(not (lo >= cse and hi <= cse + 4) for lo, hi in sec):
        print("DIAGNOSE (bitte komplett an Claude schicken):")
        print(f"  ARM9 alt: Laenge {len(a9_old)}, neu: Laenge {len(a9_new)}")
        print(f"  Modulparameter-Kennung bei {cse - 0x14 + 0x1C:#x}, Feld compressed_static_end bei {cse:#x}:"
              f" alt={u32(a9_old, cse):#x}, neu={u32(a9_new, cse):#x}")
        print(f"  Abweichende Bereiche in den ersten 0x4000 Bytes: {[(hex(x), hex(y)) for x, y in sec][:10]}")
        print(f"  Kopf: ARM9-Offset {u32(old_rom, 0x20):#x}, Groesse {u32(old_rom, 0x2C)}")
        raw = old_rom[u32(old_rom, 0x20):u32(old_rom, 0x20) + 16]
        print(f"  Erste ARM9-Bytes (alt, roh): {bytes(raw).hex()}")
        print(f"  Letzte ARM9-Bytes (alt, roh): "
              f"{bytes(old_rom[u32(old_rom, 0x20) + u32(old_rom, 0x2C) - 12:u32(old_rom, 0x20) + u32(old_rom, 0x2C)]).hex()}")
        sys.exit("Secure Area unerwartet veraendert. Nichts geschrieben.")
    if u16(old_rom, 0x6C) == crc16(a9_old[:0x4000]):
        assert u16(new_rom, 0x6C) == crc16(a9_new[:0x4000]), "Secure-Area-CRC nicht nachgezogen"
    allowed = [(cave, cave + len(CC.CAVE_BLOB)), (cse, cse + 4)]
    for lo, hi in diff_ranges(a9_old, a9_new):
        assert any(s0 <= lo and hi <= s1 for s0, s1 in allowed), "ARM9 ausserhalb der Stellen veraendert"
    assert a9_new[cave:cave + len(CC.CAVE_BLOB)] == cave_blob(test_items), "Zusatzcode falsch"
    assert u32(a9_new, cse) == 0, "ARM9 noch als komprimiert markiert"
    assert u32(new_rom, 0x2C) == len(a9_new), "ARM9-Groesse im Kopf falsch"


def main(src, dst, test_items=None, quiet=False, ground=None, rand=None):
    if os.path.abspath(src) == os.path.abspath(dst):
        sys.exit("Ziel darf nicht die Original-ROM sein.")
    with open(src, "rb") as f:
        rom = f.read()
    new_rom, old_entries, new_entries, texts = patch_rom(rom, test_items, quiet, ground, rand)
    verify(rom, new_rom, texts, test_items, quiet)
    with open(dst, "xb") as f:
        f.write(new_rom)
    print(f"Fertig: {dst} ({len(new_rom)} Bytes). Original unveraendert.")
    print("Charms (Edelsteine):")
    for bit, ids in GROUPS:
        print(f"  {GROUP_TEXT[bit][0]}: {len(ids)} Items (Nr. {ids[0]}-{ids[-1]})")
    if test_items:
        print("TESTMODUS: Der Effekt haengt zusaetzlich nur an den Items " + ", ".join(str(x) for x in test_items))
    print("Wirkung: beim naechsten wilden Pokemon wird je 1 Charm aus dem Beutel verbraucht.")
    print(f"Finden: wilde Pokemon tragen mit Chance 1 zu {FIND_RATE} einen zufaelligen Charm.")
    if quiet:
        n = sum(texts[k][4] for k in DIALOG_NARCS if k in texts)
        print(f"Dialoge: {n} gesprochene Textzeilen durch '.' ersetzt.")
    if rand and rand["wild"]:
        print(f"Wilde Begegnungen: {len(texts['wild'][4])} Arten neu zugeordnet (Zufall-Startwert {rand['seed']}).")
    if rand and rand["starters"]:
        print("Starter (Pokedex-Nummern): " + ", ".join(str(x) for x in texts["starters"]))
    if ground:
        info = texts["scripts"][4]
        if ground.get("balls"):
            print(f"Baelle auf dem Boden: {len(info['balls'])} von 400 sind jetzt Charms "
                  f"({ground['balls']} %, Zufall-Startwert {ground['seed']}).")
        if ground.get("hidden"):
            print(f"Versteckte Items: {len(info['hidden'])} von 213 sind jetzt Charms "
                  f"({ground['hidden']} %, Zufall-Startwert {ground['seed']}).")


if __name__ == "__main__":
    args = sys.argv[1:]
    items = None
    if "--test-items" in args:
        k = args.index("--test-items")
        try:
            items = tuple(int(x) for x in args[k + 1].split(","))
        except (IndexError, ValueError):
            sys.exit(__doc__)
        if len(items) != 4 or not all(1 <= x <= 255 for x in items) or len(set(items)) != 4:
            sys.exit("--test-items: genau vier verschiedene IDs zwischen 1 und 255, z. B. 17,18,19,20")
        del args[k:k + 2]
    seed = random.SystemRandom().randrange(1, 10**6)
    if "--seed" in args:
        k = args.index("--seed")
        try:
            seed = int(args[k + 1])
        except (IndexError, ValueError):
            sys.exit(__doc__)
        del args[k:k + 2]
    ground = None
    for flag, key in (("--ground-charms", "balls"), ("--hidden-charms", "hidden")):
        if flag in args:
            k = args.index(flag)
            try:
                pct = float(args[k + 1])
            except (IndexError, ValueError):
                sys.exit(__doc__)
            if not 0 < pct <= 100:
                sys.exit(f"{flag}: Prozent zwischen 1 und 100 (z. B. 20).")
            del args[k:k + 2]
            ground = ground or {"seed": seed}
            ground[key] = pct
    rand = {"wild": "--random-wild" in args, "starters": "--random-starters" in args,
            "legendary": "--allow-legendary" in args, "seed": seed}
    for flag in ("--random-wild", "--random-starters", "--allow-legendary"):
        if flag in args:
            args.remove(flag)
    if not (rand["wild"] or rand["starters"]):
        rand = None
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
    main(args[0], args[1], items, quiet, ground, rand)
