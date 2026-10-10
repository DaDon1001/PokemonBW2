#!/usr/bin/env python3
"""Liest eine .nds-Datei NUR lesend aus und gibt Text-Infos aus (keine ROM-Daten).

Aufruf:  python3 tools/inspect_nds.py pfad/zur/rom.nds > report.txt
Den Inhalt von report.txt kann man weitergeben, ohne die ROM zu teilen.
"""
import hashlib
import struct
import sys


def u16(b, o): return struct.unpack_from("<H", b, o)[0]
def u32(b, o): return struct.unpack_from("<I", b, o)[0]


def crc16(data, init=0xFFFF):
    crc = init
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def sha1(data): return hashlib.sha1(data).hexdigest()


def parse_fnt(rom, fnt_off, fnt_size):
    """Gibt {file_id: pfad} zurueck."""
    fnt = rom[fnt_off:fnt_off + fnt_size]
    total_dirs = u16(fnt, 6)
    paths = {}

    def walk(dir_id, prefix):
        entry = (dir_id & 0xFFF) * 8
        sub_off, file_id = u32(fnt, entry), u16(fnt, entry + 4)
        pos = sub_off
        while pos < len(fnt):
            n = fnt[pos]
            pos += 1
            if n == 0:
                break
            length, is_dir = n & 0x7F, bool(n & 0x80)
            name = fnt[pos:pos + length].decode("ascii", "replace")
            pos += length
            if is_dir:
                sub_id = u16(fnt, pos)
                pos += 2
                walk(sub_id, prefix + name + "/")
            else:
                paths[file_id] = prefix + name
                file_id += 1

    if total_dirs:
        walk(0xF000, "")
    return paths


def main(path):
    with open(path, "rb") as f:
        rom = f.read()
    print(f"Datei: {path}")
    print(f"Groesse: {len(rom)} Bytes ({len(rom) / 1048576:.1f} MiB)")
    print(f"SHA1 gesamt: {sha1(rom)}")

    title = rom[0:12].rstrip(b"\0").decode("ascii", "replace")
    code = rom[0x0C:0x10].decode("ascii", "replace")
    print(f"Titel: {title}   Gamecode: {code}   Version: {rom[0x1E]}   Unitcode: {rom[0x12]:#x}")
    used = u32(rom, 0x80)
    print(f"Genutzter ROM-Bereich laut Header: {used} Bytes ({used / 1048576:.1f} MiB)")
    ok = crc16(rom[:0x15E]) == u16(rom, 0x15E)
    print(f"Header-CRC16: {'ok' if ok else 'FALSCH (Header veraendert/defekt?)'}")

    a9_off, a9_entry, a9_ram, a9_size = (u32(rom, o) for o in (0x20, 0x24, 0x28, 0x2C))
    a7_off, a7_entry, a7_ram, a7_size = (u32(rom, o) for o in (0x30, 0x34, 0x38, 0x3C))
    arm9 = rom[a9_off:a9_off + a9_size]
    print(f"ARM9: offset={a9_off:#x} ram={a9_ram:#x} entry={a9_entry:#x} size={a9_size}  sha1={sha1(arm9)}")
    print(f"ARM7: offset={a7_off:#x} ram={a7_ram:#x} entry={a7_entry:#x} size={a7_size}")
    # Komprimierte ARM9 (BLZ) haben einen Footer, dessen Wert auf Kompression hindeutet.
    if len(arm9) >= 8 and u32(arm9, len(arm9) - 4) not in (0, 0xFFFFFFFF):
        print("Hinweis: ARM9-Footer sieht nach BLZ-Kompression aus (muss vor dem Patchen entpackt werden).")

    fnt_off, fnt_size, fat_off, fat_size = (u32(rom, o) for o in (0x40, 0x44, 0x48, 0x4C))
    ov9_off, ov9_size = u32(rom, 0x50), u32(rom, 0x54)
    fat = [(u32(rom, fat_off + i * 8), u32(rom, fat_off + i * 8 + 4)) for i in range(fat_size // 8)]

    print(f"\nARM9-Overlays: {ov9_size // 32}")
    print("id  ram_addr  ram_size  file_id  dateigroesse  sha1")
    for i in range(ov9_size // 32):
        e = ov9_off + i * 32
        oid, ram, rsize, _bss, _s, _e, fid = (u32(rom, e + k * 4) for k in range(7))
        s, en = fat[fid]
        print(f"{oid:3d} {ram:#010x} {rsize:9d} {fid:8d} {en - s:12d}  {sha1(rom[s:en])[:12]}")

    paths = parse_fnt(rom, fnt_off, fnt_size)
    print(f"\nDateien im Dateisystem: {len(fat)}")
    print("NARC-Archive (Pfad, Dateigroesse, Anzahl Eintraege):")
    for fid, (s, en) in enumerate(fat):
        if rom[s:s + 4] == b"NARC":
            # BTAF-Block beginnt bei 0x10, Eintragszahl bei +8
            n = u16(rom, s + 0x18) if rom[s + 0x10:s + 0x14] == b"BTAF" else -1
            print(f"  {paths.get(fid, '?')}  file_id={fid} size={en - s} eintraege={n}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
