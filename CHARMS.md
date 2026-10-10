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
- [x] Texte: `a/0/0/2`, Zeilenschluessel `0x7C89 + 0x2983*Zeile`, Zeilentabelle im Klartext. Eintrag 64 = Namen, 63 = Beschreibungen, 481/482 = weitere Namensvarianten (481 mit Steuercode-Vorspann). ROM ist eine portugiesische Fassung.
- [x] `tools/patch_charms.py`: benennt die Zeilen 179-182 um (nur Text, keine Effekte), schreibt eine neue ROM.
- [x] **Shiny Charm getestet (melonDS): wilder Encounter shiny, Charm verbraucht.** (Erst mit --test-item 17 Trank, dann mit dem echten Item 179.)
- [x] Alle vier Charm-Effekte gebaut (noch ungetestet ausser Shiny): `tools/patch_charms.py` + `tools/charm_code.py`.
  - ARM9 wird entpackt gespeichert (compressed_static_end = 0, Secure-Area-CRC nachgezogen).
  - Zusatzfunktionen (386 Bytes) in einer ungenutzten printf-Funktion bei 0x02085200.
  - Overlay 36: Einhaengestellen bei 0x021a0dca (Art/Item), 0x021a0dd6 (Shiny-Wuerfelzahl), 0x021a0e1e (IVs).
  - IV-Charm: IV-Parameter 0x3FFFFFFF statt 0xFFFFFFFF (5 Bit je Wert, alle 31).
  - Legendary/Static: Art in der Begegnungsstruktur ueberschrieben (Level bleibt wie die Begegnung).
  - Tests: `tools/dev/` (Emulator-Tests der Hilfsfunktionen mit Unicorn, Testrom-Bau).
- [x] Alle vier Charm-Effekte im Spiel getestet: funktionieren, auch kombiniert.
- [x] Poke-Markt-Lieferung gestrichen (Nutzerwunsch). Stattdessen **Finden**: Wilde Pokemon tragen mit Chance 1 zu N (Standard 20) einen zufaelligen Charm als Item (Overlay 36, 0x021a0e56 -> helper_hold). Faengt man das Pokemon, kann man das Item nehmen. Parameter `--find-rate N`.
- [ ] Weitere Fund-Quellen (Boden, versteckte Items, Kampfbelohnung) und Spielmeldungen: noch offen. Funktion zum Item-Hinzufuegen: 0x02008268 (bag,item,qty,heap).
- Hinweis: Textarchiv 40 = Festival-Missionen, 384 = C-Gear-Anrufe (nicht der Markt).
- [x] Option `--quiet-dialog`: ersetzt alle Dialogzeilen (Warte-auf-Taste-Code F000 BE01 0000) in a/0/0/2 und a/0/0/3 durch '.' + denselben Code.
- [ ] Item-Datentabelle (Berries → Charms: Name, Beschreibung, Preis, Icon)
- [ ] Code-Hooks (brauchen die genauen Adressen aus dem Report der eigenen ROM)

## Technische Funde (ROM: Schwarz 2, portugiesische Fassung, IREO)

- ARM9 ist BLZ-komprimiert (633856 Bytes entpackt, Basis 0x02004000). Overlays teils komprimiert (Flag in der Overlay-Tabelle).
- 0x0201cdd8: Shiny-Pruefung (XOR der 16-Bit-Haelften von Trainer-ID und PID, `< 8`).
- 0x0201c464 / 0x0201c4f8: Pokemon-Erzeugung, PID wird bei 0x0201c5c0 gesetzt.
- Overlay 36, Funktion bei 0x021a0dc0: erzeugt wilde Pokemon fuer den Kampf. Das Spiel hat hier schon das echte Schluesselitem Shiny Charm (0x278): Wuerfelschleife mit 1 bzw. 3 Versuchen, bricht bei der ersten Shiny-PID ab.
- Beutel: 0x02017354 (Beutel holen), 0x02008474 (HasItem), 0x0200842c (TakeItem, bag,item,qty,heap).
- Shiny-Charm-Patch (28 Bytes bei 0x021a0dd6): nimmt 1x Item 179 aus dem Beutel; war es da, wird die Wuerfelzahl 130560 -> Shiny fast sicher. Kein zusaetzlicher Platz noetig. `patch_charms.py` speichert Overlay 36 dafuer unkomprimiert.
- Ehrliche Einschraenkung: Der Charm wird automatisch beim naechsten wilden Pokemon verbraucht, solange er im Beutel liegt (kein "Benutzen"-Menue).

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
