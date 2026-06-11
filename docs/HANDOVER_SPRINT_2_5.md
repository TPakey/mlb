# Handover Sprint 2.5 — What-if Engine + Weitere Features

**Datum:** 2026-05-26
**Von:** Claude (Sprint 2.4 abgeschlossen)
**Für:** Nächste Chat-Session (Sprint 2.5)

---

## TL;DR — wo wir stehen

Sprint 2.4 ist vollständig abgeschlossen. Die beiden xfail-Integration-Tests (AC-2.3.10) bestehen jetzt regulär. Der Generator garantiert strukturell AC-2.1.8 und AC-2.1.9 für alle 30 Teams.

**Test-Stand:** Alle Sprint-2.4-Tests grün. Integration-Tests in ~20s (Budget: 60s).

---

## Was in Sprint 2.4 gemacht wurde

### AC-2.3.10: Fatigue-Constraints im Generator (✅)

**`src/generator.py`** — zwei Änderungen:

1. **CP-SAT break_days**: `break_days = ASB ∪ periodic_breaks(max_gap=21)` wenn `enforce_fatigue_constraints=True`. Pigeonhole-Garantie: max 20 konsekutive Spieltage (AC-2.1.9).

2. **SA fatigue_lambda**: `fatigue_lambda=1_000_000.0` wenn `enforce_fatigue_constraints=True`. P(accept 1-unit violation) ≈ 10⁻²⁹⁰ ≈ 0. SA fixiert AC-2.1.8-Verletzungen aktiv.

**`src/generator_optimizer.py`** — Doubleheader-Fix in `_entry_from_games`:
- `length = (games[-1].date - games[0].date).days + 1` (Tage, nicht Spiele)
- Verhindert, dass Doubleheader-Einträge fälschlicherweise Folgetage als belegt markieren

### Weitere Deliverables (✅)
- `tools/demo_pareto.py`: End-to-End Demo-Skript (CLI, JSON-Export, Tabelle)
- `tests/test_sprint_2_4.py`: 13 neue Unit-Tests (alle grün)
- `docs/SPRINT_2_4_REVIEW.md`: vollständiges Review-Dokument

---

## Offene Tasks für Sprint 2.5

### Task #22: What-if Engine (höchste Priorität)

**Was fehlt:** Eine API/Funktion, mit der MLB-Operatoren "Was wäre wenn"-Fragen stellen können:
- "Was passiert mit dem Reise-Score wenn wir NYY vs BOS am 4. Juli planen?"
- "Welche Teams werden durch eine Hallenbuchung in Houston am 15. August am stärksten betroffen?"
- "Vergleich: Plan A vs. Plan B — Delta in allen 8 Dimensionen"

**Vorschlag für Implementierung:**
```python
# src/whatif.py
def whatif_force_game(season, cfg, home, away, forced_date) -> WhatIfResult:
    """Erzwingt ein Spiel und zeigt Delta in allen Score-Dimensionen."""

def whatif_compare(season_a, season_b, teams, cfg) -> ComparisonReport:
    """Vergleicht zwei Pläne in allen 8 ParetoBundle-Dimensionen."""
```

**Datei:** `src/whatif.py` + `tests/test_whatif.py`

---

## Repository-Struktur (aktuell)

```
MLB Logistics Optimizer/
├── src/
│   ├── generator.py          # CP-SAT + SA Pipeline (Sprint 2.4 ✓)
│   ├── generator_optimizer.py # SA, Doubleheader-Fix (Sprint 2.4 ✓)
│   ├── player_fatigue.py     # AC-2.1.8/9 Validierung
│   ├── pareto.py             # Pareto-Sampling-Engine
│   ├── pareto_types.py       # ParetoBundle, ParetoPoint
│   ├── profiles.py           # ParetoProfile, PARETO_PROFILES
│   ├── tv_slots.py           # TV-Slot-Score
│   ├── event_conflicts.py    # Event-Friction
│   ├── revenue.py            # Revenue-Modell
│   └── ...
├── tools/
│   └── demo_pareto.py        # End-to-End Demo (Sprint 2.4 ✓)
├── tests/
│   ├── test_sprint_2_4.py    # 13 Tests (Sprint 2.4 ✓)
│   ├── test_fatigue_constraints.py  # inkl. 2 Integration-Tests
│   └── ...
└── docs/
    ├── SPRINT_2_4_REVIEW.md  # Aktuelles Review
    └── ...
```

---

## Wichtige Zahlen (Seed 42, Single-Thread)

| Metrik | Wert |
|---|---|
| Saison-Spiele | 2432 |
| Generator-Zeit | ~20s |
| Reise-km (nach SA) | ~1.955M km |
| AC-2.1.8 max (alle Teams) | ≤ 13 ✓ |
| AC-2.1.9 max (alle Teams) | ≤ 20 ✓ |
| Pareto-Punkte (non-dom.) | ≥ 7 |

---

## Technische Schulden (niedrige Priorität)

1. `_team_max_streaks` in SA zählt Doubleheader als 1 Spieltag (leicht konservativ vs. `player_fatigue.py`). Kein AC-Impact.
2. `num_search_workers=1` in Tests → vollständige Determinismus-Garantie, aber langsamer als Multithread.
3. Task #22 (What-if Engine) wurde von Sprint 2.4 auf Sprint 2.5 verschoben.
