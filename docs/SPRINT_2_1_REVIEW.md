# Sprint 2.1 Review — Schedule-from-Scratch Generator

**Status:** ✅ DONE
**Periode:** Abgeschlossen 2026-05-22
**Sub-Sprint:** 2.1 (von 4 in Sprint 2)

---

## Lieferung — was steht

Eine zweistufige Engine, die aus reinen Matchup-Quoten einen vollständigen
MLB-Saisonplan erzeugt:

1. **Stufe 1 — CP-SAT (`src/generator.py`):** Google OR-Tools Constraint
   Programming. Liefert einen feasiblen Plan, der alle harten Constraints
   einhält (Spiele pro Team, Heim/Auswärts-Balance, All-Star-Break,
   Saisonfenster, keine Doppelbuchungen pro Team).

2. **Stufe 2 — Simulated Annealing (`src/generator_optimizer.py`):** Nimmt
   den feasiblen CP-SAT-Plan und reduziert Reisedistanzen durch lokale
   Suche (SHIFT- und SWAP-Moves auf Serien-Start-Daten). Hält dabei alle
   harten Constraints konstant.

`generate()` orchestriert beide Stufen und gibt ein `GeneratorResult` mit
voller Diagnostik zurück (CP-SAT-Zeit, SA-Zeit, initial_km, final_km).

## Harte Zahlen (Saison 2026, single-thread, Seed 42)

| Kennzahl | Wert |
|---|---|
| Status | OPTIMAL |
| Spiele insgesamt | 2.432 |
| CP-SAT-Zeit | 0,06 s |
| Travel-Optimizer-Zeit | 16,55 s |
| **Gesamtzeit** | **16,61 s** |
| Initial km (nach CP-SAT) | 2.144.608 |
| Final km (nach SA) | 1.993.981 |
| **Travel-Verbesserung** | **7,02 %** |

## Acceptance Criteria — 10/10 grün

| # | Kriterium | Status |
|---|---|---|
| AC-2.1.1 | Plan in ≤ 30 Minuten | ✅ 16,6 s |
| AC-2.1.2 | Spiele pro Team korrekt | ✅ |
| AC-2.1.3 | Heim/Auswärts-Balance | ✅ |
| AC-2.1.4 | Matchup-Quoten erhalten | ✅ |
| AC-2.1.5 | All-Star-Break respektiert | ✅ |
| AC-2.1.6 | Saisonfenster eingehalten | ✅ |
| AC-2.1.7 | Keine Doppelbuchungen | ✅ |
| AC-2.1.10 | Total km in 1,5–2,0 Mio (Plausibilität) | ✅ 1,99 M |
| AC-2.1.11 | Reproduzierbarkeit mit Seed | ✅ Bit-identisch |
| Smoke | Mini-Szenario (2 Teams, 1 Serie) | ✅ |

> AC-2.1.8 (max 13 konsekutive Auswärtstage) und AC-2.1.9 (min 1 Off-Day
> alle 20 Spiele) sind im Charter als Property-Tests vorgesehen und derzeit
> noch nicht implementiert. Sie sind für Sub-Sprint 2.2 vorgemerkt, weil
> sie eng mit dem Disruption-Handler verzahnt werden sollen.

## Architektur-Entscheidungen — was und warum

- **Single-thread CP-SAT als Default.** Multi-threaded CP-SAT ist nicht
  deterministisch (Thread-Race auf Suchbäumen). AC-2.1.11 verlangt
  bit-identische Ergebnisse bei gleichem Seed — Single-Thread garantiert
  das. Die Performance reicht völlig (60 ms für die volle Saison).

- **SA statt CP-SAT-Objective.** Der CP-SAT erzwingt nur die harten
  Constraints; die Travel-Optimierung läuft in einer separaten Stufe.
  Vorteil: das CP-SAT-Modell bleibt einfach und schnell; das SA kann
  später um beliebige weiche Faktoren erweitert werden, ohne das
  CP-SAT-Modell zu berühren.

- **Quoten aus echten Saison-Daten.** Der `matchup_extractor` zieht die
  Matchup-Quoten aus dem MLB-2024-Schedule. Damit testen wir den
  Generator gegen genau die Asymmetrien, die in echten Saisons vorkommen
  (161/163-Spiele-Teams etc.).

## Was offen bleibt für Sub-Sprint 2.2 (Disruption Handler)

- AC-2.1.8 (Konsekutive Auswärtstage) und AC-2.1.9 (Off-Day-Frequenz)
  als Property-Tests einbauen.
- Disruption-Engine, die einen Plan + Event nimmt und alternative
  Pläne mit Tradeoff-Bewertung zurückgibt.
- Hurricane-Milton-Szenario als End-to-End-Test.

## Files in dieser Lieferung

```
src/
  generator.py                 CP-SAT + Pipeline-Orchestration (215 Zeilen)
  generator_optimizer.py       Simulated Annealing (309 Zeilen)
  matchup_extractor.py         Quoten-Extraktor (105 Zeilen)
tests/
  test_generator.py            10 Acceptance-Tests (alle grün)
docs/
  SPRINT_2_1_REVIEW.md         dieses Dokument
```
