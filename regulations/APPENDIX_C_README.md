# Appendix C — Travel Times for Scheduling (offizielle Reisezeit-Matrix)

**Quelle:** MLB-MLBPA Basic Agreement 2022–2026, „APPENDIX C — TRAVEL TIMES FOR
SCHEDULING". Offizielles Bild von Jonas beigesteuert (2026-06-09).
**Authentizität bestätigt:** Werte stimmen mit zwei unabhängig aus realen 2025-
Startzeiten zurückgerechneten Ankern überein — **LAD↔ATL = 3:52**, **LAD↔CIN = 3:48**
(vgl. `FINDING`/`SPRINT_5_DATA_FINDINGS`). Rating: **A1**.

## Format
- 30×30-Matrix der **In-Flight-Zeiten** zwischen MLB-Städten, Format `H:MM` (z. B.
  `3:11`) bzw. `:MM` (< 1 h, z. B. `:43`). Diagonale = 0.
- **Symmetrisch:** Zeit(A→B) = Zeit(B→A). Das ist der eingebaute Verifikations-Check
  bei der Transkription (jeder Wert erscheint zweimal; Abweichung = Tippfehler).
- Team-Codes (Spalten/Zeilen): ARI ATL BAL BOS CHI(=Cubs) CIN CLE COL CWS(=White Sox)
  DET HOU KC LAA LAD MIA MIL MIN NYM NYY OAK PHI PIT SD SF STL SEA TB TEX TOR WSH.

## Verwendung im Projekt
- **V(C)(8) Getaway-Startzeit** (Sprint 5.1/A3): späteste Startzeit
  = 19:00 − max(0, In-Flight − 2:30). Braucht diese Matrix als Lookup.
- **V(C)(9), V(C)(11)** nutzen ebenfalls In-Flight-Schwellen (1:30 / 2:30).
- Ersetzt den bisherigen Haversine-/Charter-Schätzer als **offizielle** Referenz.

## Offene Aufgabe (Sprint 5.1, verifikations-gegatet)
1. PNG in diesen Ordner legen (`appendix_c_travel_times.png`) — authentische Provenienz.
2. Matrix **zellweise** transkribieren nach `data/appendix_c_travel_times.json`
   (Schema: `{"ARI": {"ATL": "3:11", ...}, ...}`, Minuten als Integer ableitbar).
3. **Verifikation:** (a) Symmetrie-Check (A→B == B→A für alle Paare); (b) Anker-Check
   (LAD-ATL=3:52, LAD-CIN=3:48); (c) Stichprobe 10 Zellen visuell gegen das Bild.
   Erst nach grünem Check als Produktionsdatum freigeben.
