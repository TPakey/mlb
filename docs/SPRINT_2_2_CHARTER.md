# Sprint 2.2 Charter — Disruption Handler

**Periode:** 2026-05-22 bis 2026-06-05 (1,5–2 Wochen)
**Wertversprechen:** Resilienz — "Hurricane in Miami nächste Woche, was sind meine Optionen?"

---

## Was wir bauen

Eine Engine, die einen bestehenden Saisonplan plus ein Disruption-Event
entgegennimmt und in **≤ 60 Sekunden** drei substanziell verschiedene
Alternativ-Pläne mit Tradeoff-Bewertung liefert. Demo-Szenario: Hurricane
Milton 2024, Tropicana Field unbenutzbar für die gesamte 2025-Saison.
Unsere drei Strategien werden gegen die echte MLB-Reaktion benchmarkt
(siehe `MILTON_GOLD_STANDARD.md`).

## Die drei Strategien — bewusst diverse Mechanik

| Strategie | Mechanik | Stärke | Schwäche |
|---|---|---|---|
| **A — Postpone-to-Next-Off-Day** | Local Repair: nur betroffene Spiele auf nächste freie Tage schieben | Mindestabweichung; Plan-Rest bit-identisch | findet keine globalen Optima |
| **B — Constrained Re-Generate** | Voller CP-SAT + SA Pipeline mit "no game in disruption window" Constraint | beste globale km-/Revenue-Werte | hohe Plan-Abweichung |
| **C — Venue-Swap mit Revanche** | Disruption-Spiele werden zu Auswärts-Spielen am Gegner-Stadion; symmetrische Revanche-Serie später in der Saison (Heimrecht-Tausch) | Spiele finden trotzdem statt; Revenue verschoben statt verloren | räumliche Komplexität, Spieler-Reise |

**Wichtig:** Die ursprünglich angedachte Doubleheader-Strategie wurde
verworfen — die Recherche zeigt, dass Single-Admission-Doubleheader das
Gate-Revenue halbieren und MLB-Teams sie systematisch vermeiden (siehe
`REVENUE_MODEL_RESEARCH.md`).

## Architektur

```
src/
  disruption_types.py     Typed dataclasses: StadiumBlackout, WeatherWindow, 
                          MassPostponement, Alternative, TradeoffReport
  disruption.py           Disruption-Engine, dispatcht zu Strategien A/B/C
                          und sammelt Tradeoff-Bewertung
  repair_local.py         Strategie A: Local Repair
  repair_regenerate.py    Strategie B: Constrained Re-Generate
  repair_venue_swap.py    Strategie C: Venue-Swap + Revanche
  revenue.py              Revenue-Modell (siehe Research-Doc)
  player_fatigue.py       Konsekutive-Auswärtstage und Off-Day-Frequenz
                          als Score-Komponenten (NEU)
tests/
  test_disruption_types.py
  test_repair_strategies.py
  test_revenue_model.py
  test_fatigue_constraints.py    AC-2.1.8 + AC-2.1.9 als Property-Tests
  test_e2e_milton.py             Milton-Szenario mit historischem Vergleich
data/
  revenue_model.json             Modell-Parameter (base_team, factors)
  milton_scenario.json           Disruption-Definition + historische Lösung
docs/
  MILTON_GOLD_STANDARD.md        recherchiert
  REVENUE_MODEL_RESEARCH.md      recherchiert
  SPRINT_2_2_CHARTER.md          dieses Dokument
```

## Acceptance Criteria — alle müssen grün sein

| # | Kriterium | Test |
|---|---|---|
| AC-2.2.1 | **≤ 60 s** Response-Zeit für Standard-Disruption (1 Heimserie) | Timer-Test |
| AC-2.2.2 | Liefert **genau 3 valide** Alternativen (A, B, C) | Unit-Test |
| AC-2.2.3 | Jede Alternative hält **alle harten Constraints** ein (alle CP-SAT-Constraints aus 2.1; AC-2.1.8/9 mindestens nicht schlechter als Original-Plan) | Validator-Test |
| AC-2.2.4 | **Score-Bundle pro Alternative**: km, affected_teams, revenue_delta_usd, fatigue_delta, change_pct, hard_constraint_violations=0 | Output-Schema-Test |
| AC-2.2.5 | **Mindestabweichung-Modus**: Strategie A ändert ≤ 5 % der Originalspiele | Diff-Test |
| AC-2.2.6 | **Hurricane-Milton-E2E**: Alle drei Strategien produzieren valide Pläne; Diff-Report gegen echte MLB-Reaktion liegt vor | End-to-End-Test |
| AC-2.2.7 | **Idempotenz**: gleicher Seed → bit-identisches Ergebnis pro Strategie | Reproducibility-Test |
| AC-2.2.8 | **Alternativen-Diversität**: A vs. B vs. C haben paarweise ≥ X % unterschiedliche Spiele (X TBD nach erstem Lauf) | Diversity-Test |
| AC-2.2.9 | **Revenue-Modell-Validierung**: Modell auf 2024-Plan summiert auf 3,1–3,7 Mrd. USD (Liga-Total ±10 % vom Ist 3,41 Mrd.); LAD und NYY innerhalb ±20 % der Sportico-Per-Game-Werte | Model-Sanity-Test |
| AC-2.2.10 | **80 % Coverage** der neuen Module (disruption*, revenue, player_fatigue) | pytest-cov |
| AC-2.2.11 | **Validatoren AC-2.1.8 + AC-2.1.9** sind implementiert und gegen Mini-Saisons unit-tested | Unit-Test |
| AC-2.2.12 | **Generator-Erweiterung** für AC-2.1.8/9 als CP-SAT-Sliding-Window: voller MLB-Saisonplan hält die Limits ein | xfail-Tests → grün |

## Reihenfolge der Umsetzung (Tasks #8 ff.)

1. **Daten- und Typen-Modell** (`src/disruption_types.py`): saubere typed
   dataclasses für alle Disruption-Varianten und Score-Bundles. Validierung
   via `__post_init__`.
2. **Revenue-Modell** (`src/revenue.py` + `data/revenue_model.json`):
   Spezifikation aus dem Research-Doc implementieren, Modell gegen
   2024-Liga-Gesamt validieren.
3. **Player-Fatigue + AC-2.1.8/9** (`src/player_fatigue.py` +
   `tests/test_fatigue_constraints.py`): nachgeholte Sprint-2.1-ACs als
   Property-Tests + Score-Funktion.
4. **Strategie A** (`src/repair_local.py`): Local Repair, einfachste
   Strategie zuerst. Sofort-Validierung mit kleinen Test-Disruptionen.
5. **Strategie B** (`src/repair_regenerate.py`): Constrained Re-Generate.
   CP-SAT-Modell aus Sprint 2.1 erweitern um Disruption-Constraint.
6. **Strategie C** (`src/repair_venue_swap.py`): Venue-Swap mit Revanche.
   Architektonisch am komplexesten — kommt zuletzt.
7. **Orchestrator** (`src/disruption.py`): dispatcht zu A/B/C, sammelt
   Tradeoff-Reports, sortiert deterministisch.
8. **E2E Milton** (`tests/test_e2e_milton.py` + `data/milton_scenario.json`):
   Demo-Test mit historischem Vergleich.

## Sprint-Review-Kriterium

Sprint 2.2 gilt als **erfolgreich abgeschlossen**, wenn:

1. Alle 12 ACs grün, automatisierte Tests beweisen das
2. **Test-Suite läuft in < 3 Minuten** (inkl. 2.1-Tests und allen 2.2-Tests)
3. **Coverage-Report** zeigt ≥ 80 % für alle neuen Module
4. **Milton-E2E-Report** liegt vor: drei Alternativen, Tradeoff-Tabelle,
   prosaischer Vergleich zur echten MLB-Reaktion
5. Sprint-2.2-Review-Dokument geschrieben mit harten Zahlen pro Strategie

## Bewusst aufgeschoben (für Sprint 2.3+)

- Wettermodell für Score-Bundle (kommt mit Pareto-Explorer)
- Concessions/Merchandise-Revenue (Sekundäreinnahmen)
- TV-Slot-Konflikte (separates Soft-Factor-Modul)
- Travel-Cost in USD (Sprint 2.3 mit Profil-spezifischer Gewichtung)
- Interaktive Disruption-UI im Dashboard (Sprint 2.3 zusammen mit
  Pareto-Plot)
