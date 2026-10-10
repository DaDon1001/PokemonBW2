#!/usr/bin/env python3
"""Erzeugt tools/charm_code.py (Maschinencode des Charm-Mods) aus build_cave.py.

Aufruf: python tools/dev/gen_charm_code.py <arm9_entpackt.bin>
(arm9_entpackt.bin = entpackter ARM9 der Original-ROM, nur fuer die Pruefsumme der Original-Bytes.)
Benoetigt: keystone-engine, capstone.
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_cave as B  # noqa: E402

# (Adresse, erwartetes Original, Ziel-Funktion, Rest der neuen Bytes)
NOP = bytes.fromhex("c046")
SITES = [
    (0x021A0DCA, "20886179", "helper_entry", b""),
    (0x021A0DD6, "2868012676f6bbfa9e2189000122042367f645fb002800d0b61c301c", "helper_count",
     NOP * 11 + bytes.fromhex("301c")),
    (0x021A0E1E, "0020c0430190", "helper_iv", bytes.fromhex("0190")),
    (0x021A0E56, "62881b48", "helper_hold", b""),
]


def main(arm9_path):
    blob, syms = B.build()
    a9 = open(arm9_path, "rb").read()
    cave = B.CAVE - 0x02004000
    sha = hashlib.sha1(a9[cave:cave + len(blob)]).hexdigest()
    ids = [off for off in range(0, len(blob) - 1, 2) if blob[off + 1] == 0x21 and blob[off] in (179, 180, 181, 182)]
    hold = syms["helper_hold"] - B.CAVE
    rate = [o for o in range(hold, hold + 0x20, 2) if blob[o] == B.FIND_RATE_DEFAULT and blob[o + 1] == 0x20]
    assert len(ids) == 4 and len(rate) == 1, (ids, rate)
    lines = []
    for addr, orig, fn, rest in SITES:
        new = B.thumb_bl(addr, syms[fn]) + rest
        assert len(new) == len(bytes.fromhex(orig)), (hex(addr), len(new))
        lines.append(f'    (0x{addr:08X}, bytes.fromhex("{orig}"),\n     bytes.fromhex("{new.hex()}")),\n')
    code = f'''"""Maschinencode fuer den Charm-Mod (automatisch erzeugt mit tools/dev/gen_charm_code.py).

Alle Funktionen sind Thumb-Code und liegen im ARM9 in einer ungenutzten Funktion
(Teil der printf-Bibliothek, nirgends referenziert) ab 0x{B.CAVE:08X}.
"""
CAVE_ADDR = 0x{B.CAVE:08X}
CAVE_BLOB = bytes.fromhex(
    "{blob.hex()}"
)
# SHA1 der {len(blob)} Original-Bytes an dieser Stelle (Sicherheitspruefung gegen andere ROM-Versionen)
CAVE_ORIG_SHA1 = "{sha}"
# Offsets (im Blob) der vier Item-IDs 179..182 (Befehl "movs r1, #id")
ITEM_ID_OFFSETS = {tuple(ids)}
# Offset (im Blob) der Fundchance "1 zu N" (Befehl "movs r0, #N"), Standard {B.FIND_RATE_DEFAULT}
FIND_RATE_OFFSET = {rate[0]}
FIND_RATE_DEFAULT = {B.FIND_RATE_DEFAULT}
HELPER_ENTRY = 0x{syms['helper_entry']:08X}
HELPER_COUNT = 0x{syms['helper_count']:08X}
HELPER_IV = 0x{syms['helper_iv']:08X}
HELPER_HOLD = 0x{syms['helper_hold']:08X}

# Einhaengestellen im Overlay 36 (Funktion, die wilde Pokemon fuer den Kampf erzeugt):
# (Adresse, erwartetes Original, neue Bytes)
OV_SITES = [
{"".join(lines)}]
'''
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "charm_code.py")
    with open(out, "w") as f:
        f.write(code)
    print("geschrieben:", os.path.normpath(out), len(blob), "Bytes, Rate-Offset", rate[0])


if __name__ == "__main__":
    main(sys.argv[1])
