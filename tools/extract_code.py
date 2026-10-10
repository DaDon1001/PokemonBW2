#!/usr/bin/env python3
"""Packt ARM9, ARM7 und alle ARM9-Overlays der ROM unveraendert in eine ZIP-Datei (nur lesend).

Aufruf:  python tools/extract_code.py "rom.nds" code.zip
Die Overlays werden so gespeichert, wie sie in der ROM liegen (ggf. noch komprimiert);
overlays.csv enthaelt die Overlay-Tabelle (RAM-Adresse, Groessen, Kompressions-Flag).
"""
import os
import struct
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inspect_nds import sha1, u32  # noqa: E402


def main(src, dst):
    with open(src, "rb") as f:
        rom = f.read()
    a9_off, a9_size = u32(rom, 0x20), u32(rom, 0x2C)
    a7_off, a7_size = u32(rom, 0x30), u32(rom, 0x3C)
    fat_off = u32(rom, 0x48)
    ov_off, ov_size = u32(rom, 0x50), u32(rom, 0x54)
    # Nitro-Footer (Magic 0x2106C0DE) direkt hinter dem ARM9?
    foot = rom[a9_off + a9_size:a9_off + a9_size + 12]
    has_footer = foot[:4] == struct.pack("<I", 0x2106C0DE)
    # Beim ARM9 den Footer (12 Bytes) mitnehmen, falls vorhanden
    arm9 = rom[a9_off:a9_off + a9_size + (12 if has_footer else 0)]
    info = [f"arm9 offset={a9_off:#x} size={a9_size} nitro_footer={has_footer} sha1={sha1(arm9)}",
            f"arm7 offset={a7_off:#x} size={a7_size}",
            f"arm9 ram={u32(rom, 0x28):#x} entry={u32(rom, 0x24):#x}"]
    csv = ["id,ram_addr,ram_size,bss_size,static_start,static_end,file_id,comp_field"]
    with zipfile.ZipFile(dst, "x", zipfile.ZIP_DEFLATED) as z:
        z.writestr("arm9.bin", arm9)
        z.writestr("arm7.bin", rom[a7_off:a7_off + a7_size])
        for i in range(ov_size // 32):
            e = ov_off + i * 32
            vals = [u32(rom, e + k * 4) for k in range(8)]
            s, en = struct.unpack_from("<II", rom, fat_off + vals[6] * 8)
            z.writestr(f"overlays/ov_{vals[0]:04d}.bin", rom[s:en])
            csv.append(",".join([str(vals[0])] + [f"{v:#x}" for v in vals[1:6]] + [str(vals[6]), f"{vals[7]:#x}"]))
        z.writestr("overlays.csv", "\n".join(csv) + "\n")
        z.writestr("info.txt", "\n".join(info) + "\n")
    print("\n".join(info))
    print(f"Fertig: {dst} ({os.path.getsize(dst) / 1048576:.1f} MiB)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
