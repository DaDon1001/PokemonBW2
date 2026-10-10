# Charm-Mod für Pokémon Schwarz/Weiß 2 (melonDS)

Ziel: ungenutzte Beeren werden zu Charms mit neuen Effekten.

| Charm | Effekt | Umsetzung (Plan) |
|---|---|---|
| Shiny Charm | Das nächste wilde Pokémon ist shiny | Flag setzen beim Item-Benutzen, Hook in der Wild-Pokémon-Erzeugung wählt PID so, dass es shiny ist, Flag danach löschen |
| 100%-IV-Charm | Das nächste wilde Pokémon hat perfekte IVs (31) | gleicher Hook, IVs auf 31 setzen |
| Legendary Charm | Nächste Begegnung ist ein legendäres Pokémon | Hook ersetzt Art und Level der Begegnung |
| Static Charm | Statische Begegnungen/Gebiete werden erzwungen | Hook auf die Begegnungstabelle |

## Stand

- [x] `tools/inspect_nds.py` – liest Header, Hashes, Overlays und NARC-Liste der ROM (nur lesend, gibt nur Text aus).
- [ ] Item-Datentabelle (Berries → Charms: Name, Beschreibung, Preis, Icon)
- [ ] Code-Hooks (brauchen die genauen Adressen aus dem Report der eigenen ROM)

## Ablauf

1. `python3 tools/inspect_nds.py meine_rom.nds > report.txt`
2. `report.txt` weitergeben (die ROM selbst bleibt lokal).
3. Daraus wird der Patch für die jeweilige ROM-Version gebaut.

## Entscheidungen

- Charms verbrauchen sich bei der Benutzung (einmaliger Effekt).
- Ersetzt werden die seltensten, praktisch nie genutzten Beeren (genaue Auswahl nach dem ROM-Report).
- Erhalt: Pro Poké-Markt gibt es kostenlos genau **einen** der vier Charms zur Auswahl. Pro Markt nur einmal (Merk-Flag pro Markt im Spielstand).

## Offene Fragen

- Gilt "ein Charm pro Markt" einmalig pro Markt (Annahme) oder einmal pro Tag/Besuch?
- Wie soll der Legendary Charm funktionieren (zufällig oder wählbar)?
- Wo im Spielstand liegt das Merk-Flag (freies Event-Flag/Work in BW2 nötig, kommt aus dem Report)?
