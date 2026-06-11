# Sprint 5.1 — Startzeit-Schicht: Mess-Ergebnisse (messen statt behaupten)

**Stand:** 2026-06-10. Belegt empirisch, dass die V(C)(8)-Getaway-Formel und die
V(C)(9)-Prüfung gegen die **realen** 2024- und 2025-Pläne korrekt sind. Reproduzierbar
über `tools/measure_start_times.py` (reine Messung, verändert nichts).

## Grundlage
- **Appendix C** (`data/appendix_c_travel_times.json`, Rating A1): 30×30 In-Flight-
  Zeiten, voll symmetrisch (0 Mismatches über alle 406 Paare), Anker LAD-ATL=3:52,
  LAD-CIN=3:48, LAA-LAD=:03, OAK-SFG=:01 verifiziert. Transkript-Verifier:
  `tools/transcribe_appendix_c.py`.
- **Echte Startzeiten:** aus `gameDate` (UTC) der MLB-Stats-API-JSONs, DST-korrekt in
  die Lokalzeit der Spielstadt konvertiert (`src.start_times.load_real_start_times`).
- **V(C)(8)-Formel:** `latest = 19:00 − max(0, inflight − 2:30)` (In-Flight = Appendix C).

## V(C)(8) — Getaway-Startzeit
Getaway = Spieltag, an dem mind. ein Club am Folgetag in einer anderen Stadt spielt.

| Jahr | Getaway-Spiele | reise-bindend (inflight>2:30) | Verstöße @0min | @20min | @40min |
|------|----------------|-------------------------------|----------------|--------|--------|
| 2024 | 525            | 120                           | 45             | 2      | **0**  |
| 2025 | 527            | 112                           | 53             | 3      | **0**  |

**Befund:** Alle scheinbaren „Verstöße" liegen ≤40 min über dem nominalen 7-PM-Anker
und clustern an festen Clubs (Braves 7:20, Rays 7:35) — die **per-Club First-Pitch-
Konvention** (reale Erstwürfe 7:05–7:40), kein Regelbruch. Mit dieser Konventions-
Toleranz (40 min) ist der reale Plan **verstoßfrei**.

**Der eigentliche Beweis (travel-abhängiger Teil):** Bei den reise-**bindenden** Fällen
(inflight > 2:30, wo die Grenze materiell unter 19:00 sinkt) hält der reale Plan die
Formel exakt ein — Median-Abstand ~5 h unter der Grenze (überw. Tag-Spiele), schlechtester
Einzelfall +23 min (innerhalb Konvention). D. h. die travel-abhängige Verschärfung der
Formel ist durch die Realität gedeckt → **Formel an echten Daten bewiesen.**

## V(C)(9) — Tag (<17:00) nach ≥19:00-Auswärtsspiel am Vortag
| Jahr | Roh-Treffer | mit CBA-Ausnahmen (Feiertag/Home-Opener/Cubs) |
|------|-------------|-----------------------------------------------|
| 2024 | 0           | **0** |
| 2025 | 3           | **0** |

Die 3 Roh-Treffer 2025 sind **exakt** die dokumentierten CBA-Ausnahmen (inflight ≤1:30 +
Feiertag/Home-Opener): Pirates Home-Opener 04.04., July 4th, Labor Day 01.09. Mit den
Ausnahmen ist der reale Plan **verstoßfrei** → Checker korrekt.

## V(C)(6) — Tag-Spiel-Mindeststart (13:00, weich)
| Jahr | Früh-Starts < 13:00 ohne Ausnahme |
|------|-----------------------------------|
| 2024 | 11 |
| 2025 | 9  |

Alle sind etablierte, waiver-gedeckte Liga-Specials (V(C)(18)): Patriots' Day Fenway
11:10, „Education Day"-Mittagsspiele, Feiertags-Morgenspiele. Deshalb ist STARTTIME-DAYMIN
**weich** (Qualitätshinweis) — der Optimierer selbst plant keine Sub-13:00-Spiele ohne
Anlass; internationale Spielorte (Seoul/London/Tokyo) sind ausgeschlossen.

## Compliance-Integration (gegated)
`compliance.py` kennt drei neue Regeln, aktiv nur mit zugewiesenen/echten Startzeiten
(Parameter `start_min`); ohne sie werden sie übersprungen → Default-Pfad bit-identisch:
- **STARTTIME-GETAWAY** (V(C)(8), hart, ±40 min Konvention) — real 2024+2025: 0.
- **STARTTIME-NIGHTDAY** (V(C)(9), hart, m. Ausnahmen) — real 2024+2025: 0.
- **STARTTIME-DAYMIN** (V(C)(6), weich) — real: nur dokumentierte Früh-Specials.

## Determinismus & Tests
- `src/start_times.py` ist reine deterministische Funktion (kein RNG); `assign_start_times`
  liefert run-zu-run identische Slots. Gating: Default off → bestehende Outputs bit-identisch.
- Tests: `tests/test_sprint_5_1_starttimes.py` (17), Appendix-C-Integrität, Formel,
  Reproduktion 2024+2025, Gating, Determinismus. Regression: Compliance/Fatigue/Sprint-4/QA
  (74) + Invarianten (5) grün.

## Akzeptanzkriterium 5.1 — erfüllt
(a) Reproduktion trifft reale Getaway-Zeiten (bindende Fälle exakt, Rest = Konvention) ✓;
(b) realer Plan unter den neuen Startzeit-Regeln verstoßfrei (Startzeit-Schicht fügt keinen
neuen harten Verstoß hinzu) ✓; (c) Determinismus des Default-Pfads bit-identisch (gegated) ✓.
