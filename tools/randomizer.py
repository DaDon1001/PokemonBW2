"""Zufallsfunktionen fuer wilde Begegnungen und Starter (Schwarz 2, ROM-Daten).

Wilde Begegnungen: a/1/2/7, je Gebiet 232 Bytes (bei Jahreszeiten-Gebieten 4 x 232):
  8 Bytes Raten, danach 56 Slots zu je 4 Bytes: u16 (Art in Bits 0-10, Form in Bits 11-15), u8 min, u8 max.
Starter: Tabelle [495, 498, 501] (Schnivy, Floink, Ottaro) im Overlay 316 bei 0x0219FA94.
"""
import random
import struct

BLOCK = 232
SLOTS = 56
SLOT_START = 8
MAX_SPECIES = 649

# Legendaere und mythische Pokemon (Nr. im Nationalen Pokedex, Gen 1-5)
LEGENDARY = ({144, 145, 146, 150, 151, 243, 244, 245, 249, 250, 251}
             | set(range(377, 387)) | set(range(480, 495)) | set(range(638, 650)))

STARTER_OV_ID = 316
STARTER_OV_RAM = 0x0219CE80
STARTER_OV_SIZE = 0x2FA0
STARTER_TABLE_ADDR = 0x0219FA94
STARTER_ORIGINAL = (495, 498, 501, 7466, 7552, 7635)


def species_pool(allow_legendary):
    return [s for s in range(1, MAX_SPECIES + 1) if allow_legendary or s not in LEGENDARY]


def wild_blocks(data):
    if len(data) % BLOCK:
        raise ValueError("Begegnungs-Datei hat unerwartete Groesse")
    return len(data) // BLOCK


def species_in_wild(entries):
    seen = set()
    for data in entries:
        for b in range(wild_blocks(data)):
            for s in range(SLOTS):
                sp = struct.unpack_from("<H", data, b * BLOCK + SLOT_START + 4 * s)[0]
                if 1 <= (sp & 0x7FF) <= MAX_SPECIES:
                    seen.add(sp & 0x7FF)
    return seen


def make_mapping(seen, pool, rng):
    """Jeder vorkommenden Art wird eine zufaellige andere (moeglichst eindeutige) Art zugeordnet."""
    seen = sorted(seen)
    if len(pool) >= len(seen):
        targets = rng.sample(pool, len(seen))
    else:
        targets = [rng.choice(pool) for _ in seen]
    return dict(zip(seen, targets))


def randomize_wild(entries, mapping):
    """Gibt neue Eintraege zurueck: Art laut mapping, Form 0, Level und Raten unveraendert."""
    out = []
    for data in entries:
        buf = bytearray(data)
        for b in range(wild_blocks(data)):
            for s in range(SLOTS):
                off = b * BLOCK + SLOT_START + 4 * s
                sp = struct.unpack_from("<H", buf, off)[0]
                if (sp & 0x7FF) in mapping:
                    struct.pack_into("<H", buf, off, mapping[sp & 0x7FF])
        out.append(bytes(buf))
    return out


def pick_starters(pool, rng):
    return tuple(rng.sample(pool, 3))
