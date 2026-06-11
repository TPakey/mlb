# Sprint 5.2 — Compliance-Vollständigkeit: Mess-Ergebnisse

**Stand:** 2026-06-10. Schließt die strukturellen Article-V-Regeln und sichert den
SA-Move-Set gegen stille harte Verstöße. Reproduzierbar über
`tools/measure_start_times.py` (Startzeit) und die 5.2-Tests.

## Neue Checks
- **V(C)(13) Off-Day-Verteilung** (`src/schedule_rules.check_offday_distribution`):
  ≤2 Open Days/7-Tage-Fenster (All-Star-Break ausgenommen), ≥7 in letzten 67, ≥3 in
  letzten 32 Tagen.
- **V(C)(14)/(15) Doubleheader-Limits** (`check_doubleheader_limits`): keine DH an
  Folgetagen; Twi-Night-DH (erstes Spiel ≥16:00) ≤3/Heimclub und nicht am Getaway-Tag.
- Beide als Compliance-Regeln `CBA-OFFDAY`/`CBA-DH` verdrahtet, **SOFT** (Originalplan-
  Regeln; auf as-played-Daten informativ).

## Messung gegen reale (as-played) Pläne
| Regel | 2024 | 2025 | Einordnung |
|-------|------|------|-----------|
| V(C)(13) Off-Day-Abweichungen | 12 | 8 | **as-played-Artefakte** (Saisonauftakt-Reise-Gaps, Rainout-Cluster z. B. COL 17.–23.04.2025) — keine echten Verstöße |
| V(C)(14) DH an Folgetagen | 0 | 4 | 2025 = **Rainout-Makeup-DHs** (BAL/BOS 23./24.05., CHC/MIL 18./19.08.) |
| V(C)(15) Twi-Night | 0 | 0 | sauber |

**Befund:** V(C)(13)/(14) gelten für den **Originalplan**; die `mlb_schedule_*.json`
sind as-played (Makeups/Relokationen/Intl) → die Abweichungen sind Artefakte, keine
Regelbrüche (deckt sich mit `finding-as-played-data` und dem A2-Befund). Deshalb SOFT
im Standard-Report; **harte Durchsetzung** erfolgt als Guard auf Optimierer-Output
(`schedule_rules.original_schedule_violations`).

## Querschnitt — kein stiller harter Verstoß durch SA-Moves (wichtigster Befund)
Beim Bau der Post-Output-Validierung zeigte sich: der SA-Optimierer (`optimize_travel`,
Warm-Start real 2024) **erzeugte einen neuen `CBA-PTET`-Verstoß** (V(C)(11) Pacific→
Eastern ohne Off-Day) — der Feasibility-Penalty deckte nur den km/TZ-Envelope ab, nicht
die spezifische PT→ET-Regel. Das ist exakt die „stille Verletzung", vor der das
Gap-Register warnt.

**Fix (gegated, deterministisch):** neuer SA-Penalty-Term `feas_w_ptet`
(`OptimizerConfig`, `optimize_pareto`, CLI `--feas-ptet`) addiert eine Strafe je
konsekutivem Spieltag PT-Stadt → ET-Stadt ohne Off-Day, eingebettet in die bestehende
per-Team-Feasibility-Maschinerie (Apply/Revert). **Default 0.0 → bit-identisch**;
empfohlener Aktiv-Wert ~100 (× `feas_lambda` dominiert km klar). Mit aktivem Penalty
führt der Optimierer **keinen neuen harten Verstoß** mehr ein (Property-Test grün,
deterministisch).

## V(C)(5) — bewusst nicht hart geprüft (Datengrenze)
V(C)(5) („kein Start nach 17:00, wenn ein Club am Folgetag eine **Day-Doubleheader**
spielt") braucht eine zuverlässige Day-DH-Typ-Klassifikation (Split/Traditional/Day vs.
Twi-Night), die der Loader nicht erhält. → als Datengrenze dokumentiert; in der Praxis
ohnehin durch V(C)(8)-Getaway-Cap mitgedeckt.

## Tests
- `tests/test_sprint_5_2_compliance.py` (14): synthetische Checker-Logik (Off-Day-Fenster,
  Folgetag-DH, Twi-Night-Getaway), reale Messung (Twi-Night 0; 2025-DH = nur Folgetag-
  Makeups), SOFT-Wiring (real 2024 bleibt is_compliant), Post-Output-Property
  (kein neuer harter Verstoß) + PTET-Determinismus. Regression (5.1/Compliance/Pareto/
  Fatigue/Invarianten/Sprint-4) grün; Default-Pfad bit-identisch.

## Akzeptanz 5.2
A2 (als Guard, as-played-Limitation dokumentiert) ✓; A3 (V(C)(8)/(9) in 5.1, V(C)(15)
hier) ✓; A4 (V(C)(14)/(15)) ✓; Querschnitt „kein Move bricht still eine harte Regel" ✓
(PTET-Lücke gefunden + gegated geschlossen). Alles gegen 2024+2025 gemessen.
