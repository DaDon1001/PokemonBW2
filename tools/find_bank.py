#!/usr/bin/env python3
"""Bewertet alle Text-Archive (a/0/0/2) nach typischen Poke-Markt-Woertern und zeigt die besten.

Aufruf:  python tools/find_bank.py rom.nds > bank.txt
Je mehr verschiedene Marktwoerter (Begruessung, Menge, Preis, Danke ...) in einem Archiv
vorkommen, desto hoeher der Rang. Ausgegeben werden die besten 8 Archive mit Beispielzeilen.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dump_items import read_narc  # noqa: E402
from dump_text import decode_line  # noqa: E402
from inspect_nds import parse_fnt, u16, u32  # noqa: E402

WORDS = ["bem-vind", "em que posso", "quantos", "aqui est", "obrigad", "dinheiro", "comprar",
         "vender", "mais alguma", "mochila", "volte", "não tem espa", "preço", "deseja",
         "gostaria", "algo mais", "loja", "venda", "compra"]


def main(path):
    with open(path, "rb") as f:
        rom = f.read()
    paths = parse_fnt(rom, u32(rom, 0x40), u32(rom, 0x44))
    fid = next(i for i, p in paths.items() if p == "a/0/0/2")
    s, e = struct.unpack_from("<II", rom, u32(rom, 0x48) + fid * 8)
    entries = read_narc(rom, s, e)
    ranking = []
    for idx, data in enumerate(entries):
        if len(data) < 0x14 or u16(data, 0) != 1:
            continue
        n, base = u16(data, 2), u32(data, 0x0C)
        if n == 0 or n > 400 or base + 4 + n * 8 > len(data):
            continue
        found, lines = set(), []
        for i in range(n):
            try:
                t = decode_line(data, base, i)
            except Exception:
                break
            low = t.lower()
            hit = [w for w in WORDS if w in low]
            if hit:
                found.update(hit)
                if len(lines) < 8:
                    lines.append((i, t[:110]))
        if found:
            ranking.append((len(found), idx, n, sorted(found), lines))
    ranking.sort(key=lambda r: (-r[0], r[2]))
    for score, idx, n, found, lines in ranking[:8]:
        print(f"== Archiv {idx} ({n} Zeilen), {score} verschiedene Woerter: {', '.join(found)}")
        for i, t in lines:
            print(f"   Zeile {i}: {t}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
