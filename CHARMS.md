# Charm-Mod für Pokémon Schwarz/Weiß 2 (melonDS)

Ziel: ungenutzte Beeren werden zu Charms mit neuen Effekten.

| Charm | Beere (ID) | Effekt |
|---|---|---|
| Shiny Charm | Spelon (179) | Der nächste wilde Encounter ist shiny |
| 100%-IV-Charm | Pamtre (180) | Der nächste wilde Encounter hat perfekte IVs (31 in allen Werten) |
| Legendary Charm | Watmel (181) | Der nächste wilde Encounter ist ein legendäres Pokémon |
| Static Charm | Durin (182) | Der nächste wilde Encounter hat 600+ Basiswerte (BST), wie ein Static-Pokémon |

Gemeinsamer Mechanismus: Beim Benutzen wird im Spielstand ein "wartender Charm" (1 von 4) gesetzt und das Item verbraucht. Ein Hook in der Wild-Encounter-Erzeugung liest das Flag, wendet den Effekt an und löscht es danach.

## Stand

- [x] `tools/inspect_nds.py` – liest Header, Hashes, Overlays und NARC-Liste der ROM (nur lesend, gibt nur Text aus).
- [x] ROM identifiziert: Pokémon Schwarz 2 (EN), Gamecode IREO, v0, Header-CRC ok.
- [x] Item-Daten: `a/0/2/4`, 639 Einträge à **36 Bytes** (nicht 44). Feld 0x00 = Preis/10 (Trank 30 → 300, Pokéball 20 → 200). Zuordnung der Beeren-IDs (149..212) bestätigt: z. B. Lum (157) hat Status-Maske 0x3f, Pomeg-Beeren (169..174) haben -10 EV (0xf6).
- [ ] Item-Datentabelle (Berries → Charms: Name, Beschreibung, Preis, Icon)
- [ ] Code-Hooks (brauchen die genauen Adressen aus dem Report der eigenen ROM)

## Ablauf

1. `python3 tools/inspect_nds.py meine_rom.nds > report.txt`
2. `report.txt` weitergeben (die ROM selbst bleibt lokal).
3. Daraus wird der Patch für die jeweilige ROM-Version gebaut.

## Entscheidungen

- Charms verbrauchen sich bei der Benutzung (einmaliger Effekt).
- Kandidaten (Beeren ohne jeden Nutzen in Gen 5, Heil-/Kampfeffekt-Felder leer): 164..168 (Razz, Bluk, Nanab, Wepear, Pinap) und 175..183 (Cornn, Magost, Rabuta, Nomel, Spelon, Pamtre, Watmel, Durin, Belue). Vorschlag: Spelon (179), Pamtre (180), Watmel (181), Durin (182).
- Ersetzt werden die seltensten, praktisch nie genutzten Beeren (genaue Auswahl nach dem ROM-Report).
- Erhalt: Pro Poké-Markt gibt es kostenlos genau **einen** der vier Charms zur Auswahl. Pro Markt nur einmal (Merk-Flag pro Markt im Spielstand).

## Offene Fragen

- Gilt "ein Charm pro Markt" einmalig pro Markt (Annahme) oder einmal pro Tag/Besuch?
- Wie soll der Legendary Charm funktionieren (zufällig oder wählbar)?
- Wo im Spielstand liegt das Merk-Flag (freies Event-Flag/Work in BW2 nötig, kommt aus dem Report)?
