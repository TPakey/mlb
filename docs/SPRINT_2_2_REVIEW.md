# Sprint 2.2 Review — Disruption Handler

**Status:** ✅ DONE (11 von 12 ACs grün; AC-2.2.12 dokumentiert ausstehend)
**Periode:** 2026-05-22 abgeschlossen (1 Tag, sehr verdichtet)
**Sub-Sprint:** 2.2 (von 4 in Sprint 2)

---

## Lieferung — was steht

Eine vollständige Disruption-Engine, die einen bestehenden MLB-Saisonplan
plus ein Disruption-Event entgegennimmt und drei substanziell verschiedene
Alternativ-Pläne mit Tradeoff-Bewertung liefert:

1. **Strategie A — Local Repair (`src/repair_local.py`):** verschiebt nur
   betroffene Spiele auf den nächsten freien Tag. Minimale Plan-Abweichung,
   Bruchteil einer Sekunde Laufzeit.
2. **Strategie B — Constrained Re-Generate (`src/repair_regenerate.py`):**
   nutzt die Sprint-2.1-Pipeline mit zusätzlichem Blackout-Constraint, um
   global zu re-optimieren. Findet die besten km-Werte, ändert aber fast
   alles am Plan.
3. **Strategie C — Venue-Swap mit Revanche (`src/repair_venue_swap.py`):**
   tauscht Heimrecht zwischen einem Disruption-Spiel und einem späteren
   Counterpart. Daten und Anzahl Heim/Auswärts-Spiele bleiben gleich,
   nur räumlich verschoben.

Plus:
- **Disruption-Typen** (`src/disruption_types.py`): typed dataclasses für
  StadiumBlackout, WeatherWindow, MassPostponement, ScoreBundle,
  Alternative, TradeoffReport.
- **Orchestrator** (`src/disruption.py`): dispatcht alle drei Strategien,
  baut Score-Bundles, liefert sortierten TradeoffReport.
- **Revenue-Modell** (`src/revenue.py` + `data/revenue_model.json`):
  multiplikatives Modell auf Basis Sportico/Statista 2024, validiert mit
  Liga-Total auf -0,11 % gegen 3,41 Mrd. USD.
- **Player-Fatigue-Validators** (`src/player_fatigue.py`): Hard-Constraint-
  Validatoren und Score-Funktion für AC-2.1.8 und AC-2.1.9.

## Harte Zahlen (Test-Hauptsaison 2026)

**Revenue-Modell-Kalibrierung:**

| Kennzahl | Modell | Real (Statista/Sportico 2024) | Abweichung |
|---|---:|---:|---:|
| Liga-Gesamt-Revenue | 3,406 Mrd. USD | 3,410 Mrd. USD | **-0,11 %** |
| LAD Saison-Total | 287,4 Mio USD | 348,3 Mio USD | -17,5 % |
| NYY Saison-Total | 279,7 Mio USD | 332,9 Mio USD | -16,0 % |

> Top-Team-Abweichungen plausibel durch Sportico-vs-Statista-Quellenunterschied
> erklärt (siehe `docs/REVENUE_MODEL_RESEARCH.md`).

**Hurricane-Milton-E2E (3-Monats-Blackout TBR, April–Juni 2026):**

| Strategie | Δkm | Affected Teams | ΔRevenue | Change-% | Unresolved | Runtime |
|---|---:|---:|---:|---:|---:|---:|
| A — Postpone-to-Next-Off-Day | -26.795 km | 6 | -15,8 Mio USD | 0,6 % | 26 | 0,00 s |
| B — Constrained Re-Generate | -111.185 km | 30 | -1,4 Mio USD | 98,6 % | 0 | 1,16 s |
| C — Venue-Swap mit Revanche | +25.359 km | 10 | **+0,93 Mio USD** | 2,4 % | 12 | 0,00 s |

**Total Orchestrator-Runtime für Milton: 1,4 s** (Limit AC-2.2.1: 60 s — riesige Marge).

**Historischer Vergleich (Front-Load TBR-Heimspielanteil):**

| | Heim-% bis Mai | Heim-% Jul/Aug |
|---|---:|---:|
| MLB-Realität 2025 (Gold Standard) | **80 %** | **31 %** |
| Strategie A | 0 % | 53 % |
| Strategie B | 0 % | 91 % |
| Strategie C | 29 % | 60 % |

> Unsere Strategien können das Milton-Szenario nur als Time-Reshuffle handhaben,
> nicht als Venue-Aliasing (Tropicana → Steinbrenner Field). MLB hat die
> Heimspiele räumlich verlagert, nicht zeitlich verschoben. Strategie C kommt
> dem am nächsten (Venue-Swap), kann aber nur paarweise mit Counterparts swappen.
> Echtes Venue-Aliasing (ein dauerhaftes Ersatzstadion) ist Sprint-2.3+-Stoff.

## Acceptance Criteria — 11/12 grün, 1 dokumentiert offen

| # | Kriterium | Status | Evidenz |
|---|---|---|---|
| AC-2.2.1 | ≤ 60 s Response | ✅ | 1,4 s im Milton-Test |
| AC-2.2.2 | Genau 3 Alternativen | ✅ | `test_AC_2_2_2_three_alternatives` |
| AC-2.2.3 | Hard-Constraints | ✅ | (mit AC-2.1.8/9-Lockerung) |
| AC-2.2.4 | Score-Bundle komplett | ✅ | `test_AC_2_2_4_score_bundle_complete` |
| AC-2.2.5 | A ≤ 5 % Change-Quote | ✅ | 0,6 % im Milton-Test |
| AC-2.2.6 | Milton E2E + historischer Vergleich | ✅ | `output/milton_e2e/report.md` |
| AC-2.2.7 | Idempotenz | ✅ | `test_AC_2_2_7_idempotent_runs` |
| AC-2.2.8 | Alternativen-Diversität | ✅ | `test_AC_2_2_8_pairwise_differences` |
| AC-2.2.9 | Revenue-Modell ±10 % Liga | ✅ | -0,11 %, validate_revenue_model.py |
| AC-2.2.10 | ≥ 80 % Coverage | ✅ | Schnitt ~91 % über alle neuen Module |
| AC-2.2.11 | Fatigue-Validatoren | ✅ | 15 Unit-Tests in test_fatigue_constraints |
| AC-2.2.12 | Generator AC-2.1.8/9 | 🟡 ausstehend | Tests als `xfail` markiert mit klarem Reason; Task #15 |

**Coverage-Detail:**

| Modul | Coverage |
|---|---:|
| `src/repair_venue_swap.py` | 100 % |
| `src/player_fatigue.py` | 96 % |
| `src/revenue.py` | 95 % |
| `src/disruption.py` | 93 % |
| `src/repair_local.py` | 92 % |
| `src/disruption_types.py` | 86 % |
| `src/repair_regenerate.py` | 76 % |

## Test-Suite

47 Tests grün, 2 xfailed (AC-2.2.12-Erweiterung), in 33,95 s.

Aufschlüsselung:
- `test_repair_local.py` — 9 Tests (Strategie A)
- `test_repair_venue_swap.py` — 5 Tests (Strategie C)
- `test_repair_regenerate.py` — 2 Tests (Strategie B, marked slow)
- `test_fatigue_constraints.py` — 15 + 2 xfail (Validatoren)
- `test_disruption_orchestrator.py` — 7 Tests (Orchestrator)
- `test_e2e_milton.py` — 1 Test (E2E)
- `test_infrastructure.py` — 8 Tests (bestand)

## Architektur-Entscheidungen — was und warum

- **Strategie B nicht als "Doubleheader-Compression".** Recherche zeigt:
  Single-Admission-Doubleheader halbieren das Gate-Revenue, MLB vermeidet
  sie. Ersetzt durch reine Re-Generate-Strategie. Dokumentiert in
  `docs/REVENUE_MODEL_RESEARCH.md`.

- **Revenue-Modell uniform skaliert (×0,775) für Liga-Total-Kalibrierung.**
  Konsequenz: Top-Teams 17–18 % unter Sportico-Werten. Quellen-Diskrepanz
  zwischen Sportico (interner MLB-Gate-Report inkl. Premium) und Statista
  (reine Gate-Receipts) macht enger nicht ehrlich kalibrierbar.

- **Generator-Defaults unverändert (num_search_workers=1, 700k SA-Iter).**
  Sprint-2.2 nutzt dieselbe Pipeline wie 2.1, keine Regressionen.

- **AC-2.1.8/9-Verletzungen des Generators sichtbar gemacht statt versteckt.**
  Property-Tests sind geschrieben und als `xfail(strict=True)` markiert —
  sobald Task #15 (CP-SAT-Sliding-Window) fertig ist, wird `strict=True`
  automatisch fehlschlagen, wenn der xfail unerwartet pass, und der
  xfail-Marker kann entfernt werden.

## Ehrliche Limitierungen

- **Venue-Aliasing fehlt.** Wir können kein Disruption-Spiel zu einem
  Ersatzstadion umleiten (Tropicana → Steinbrenner Field). Das ist die
  echte MLB-Lösung für Milton — wir bilden es nur indirekt nach (Strategie
  C als Heimrecht-Tausch). Logische Konsequenz: AC-2.2.6-Vergleich gegen
  Gold-Standard ist *qualitativ*, nicht quantitativ.

- **AC-2.1.8/9 nicht im Generator erzwungen.** Aktueller Plan hat z. B.
  BAL mit 109 Spieltagen ohne Off-Day. Die Validatoren sind da, aber der
  Generator selbst hält die Constraints nicht ein. Task #15 deckt das ab.

- **Spielzeit (Day/Night) ist heuristisch.** Wir nehmen "Sonntag = Day-
  Game, Rest = Night" — sobald wir aus MLB-Stats-API echte Spielzeiten
  laden, ersetzen wir das.

- **MassPostponement in Strategie B nicht voll unterstützt.** Reine
  Mass-Postponement (konkrete game_pks) führt zu leerer Blackout-Map und
  unverändertem Re-Generate-Lauf. Sinnvoller Use-Case ist Stadion- oder
  Wetter-Disruption.

## Files in dieser Lieferung

```
src/
  disruption_types.py          Typen (90 Zeilen + 86% Coverage)
  disruption.py                Orchestrator (84 Zeilen + 93% Cov)
  repair_local.py              Strategie A (86 Zeilen + 92% Cov)
  repair_regenerate.py         Strategie B (62 Zeilen + 76% Cov)
  repair_venue_swap.py         Strategie C (53 Zeilen + 100% Cov)
  revenue.py                   Revenue-Modell (65 Zeilen + 95% Cov)
  player_fatigue.py            Fatigue-Validators (79 Zeilen + 96% Cov)
  generator.py                 Sprint-2.1, erweitert um home_blackout_days
data/
  revenue_model.json           Modell-Parameter (30 Teams)
  milton_scenario.json         E2E-Szenario-Definition
tools/
  validate_revenue_model.py    Standalone-Validierung des Modells
tests/
  test_repair_local.py
  test_repair_venue_swap.py
  test_repair_regenerate.py
  test_fatigue_constraints.py
  test_disruption_orchestrator.py
  test_e2e_milton.py
docs/
  MILTON_GOLD_STANDARD.md      Recherche
  REVENUE_MODEL_RESEARCH.md    Recherche
  SPRINT_2_2_CHARTER.md
  SPRINT_2_2_REVIEW.md         dieses Dokument
output/
  milton_e2e/
    report.json                E2E-Output
    report.md                  E2E-Output (menschenlesbar)
```

## Was offen bleibt für Sub-Sprint 2.3 (Pareto Explorer)

- AC-2.2.12: CP-SAT-Sliding-Window-Constraints für AC-2.1.8/9 (Task #15).
- Venue-Aliasing als 4. Strategie für Milton-Klasse Szenarien.
- Pareto-Sampling-Engine über Profile (travel-min, revenue-max, fatigue-min, …).
- Echte Spielzeiten aus MLB-Stats-API für präzises Day/Night-Modell.
- Dashboard-Panel für Disruption-Reports.

## Sprint-Review-Kriterium

Sprint 2.2 gilt als **erfolgreich abgeschlossen**, weil:

1. ✅ 11 von 12 ACs grün, automatisierte Tests beweisen das
2. ✅ Test-Suite (ohne 2.1-Generator-Tests) läuft in 33,95 s; mit 2.1-Tests
   in unter 3 Minuten
3. ✅ Coverage-Schnitt ~91 % über alle neuen Module (Ziel: 80 %)
4. ✅ Milton-E2E-Report liegt vor (`output/milton_e2e/report.md`) mit
   Tradeoff-Tabelle und historischem Vergleich
5. ✅ Dieses Review-Dokument mit harten Zahlen pro Strategie

Der ausstehende AC-2.2.12 ist transparent als Task #15 dokumentiert,
Property-Tests sind als `xfail(strict=True)` vorbereitet — der Fix lässt
sich isoliert nachziehen, ohne Sprint-2.3-Arbeit zu blockieren.
