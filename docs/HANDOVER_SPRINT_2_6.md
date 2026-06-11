# Handover Sprint 2.6

**Datum:** 2026-05-26
**Von:** Claude (Sprint 2.5 abgeschlossen)
**Für:** Nächste Chat-Session

---

## TL;DR

Sprint 2.5 ist abgeschlossen. Die **What-if Engine** (`src/whatif.py`) ist vollständig implementiert, getestet (44/44 Unit-Tests grün, 0.56s) und dokumentiert.

Das System kann jetzt:
1. **Vollständige Saisonpläne generieren** (CP-SAT + SA, ~20s, AC-2.1.8/9-konform für alle 30 Teams)
2. **Pareto-Front über 8 Dimensionen** berechnen (6 Anker + Interior-Punkte)
3. **What-if-Szenarien** in < 2s analysieren (Force Serie, Blackout, Plan-Vergleich)

---

## Was in Sprint 2.5 gebaut wurde

### `src/whatif.py` — 4 öffentliche Funktionen

```python
# Szenario 1: Termin erzwingen
result = whatif_force_series(season, teams, cfg,
    home="NYY", away="BOS", forced_start=date(2026, 7, 4))
print(result.summary())

# Szenario 2: Venue-Blackout
result = whatif_blackout(season, teams, cfg,
    team="HOU",
    blackout_dates=[date(2026, 8, 15), date(2026, 8, 16)],
    reason="Konzert")
print(result.summary())

# Szenario 3: Plan-Vergleich
result = whatif_compare(season_balanced, season_travel_min, teams,
    "Balanced", "Travel-Optimiert")
print(result.summary())

# Bonus: Team-Impact
impact = analyze_team_impact(original_season, modified_season, "NYY")
print(f"NYY: +{impact.games_added}/-{impact.games_removed} Spiele, "
      f"Travel-Delta: {impact.travel_delta_km:+.0f} km")
```

Jede Funktion gibt ein `WhatIfResult` zurück mit:
- `original_bundle` + `modified_bundle` (ParetoBundle, alle 8 Dimensionen)
- `deltas` (DimensionDelta-Liste mit direction: better/worse/neutral)
- `modified_season` (direkt weiterverwendbar)
- `feasible` + `warnings`

### `tests/test_whatif.py` — 44 Tests, 0.56s

---

## Aktuelle Datei-Struktur

```
src/
├── generator.py              # CP-SAT + SA (enforce_fatigue_constraints=True default)
├── generator_optimizer.py    # SA + Doubleheader-Fix
├── player_fatigue.py         # AC-2.1.8/9 Validierung
├── pareto.py                 # sample_pareto_frontier()
├── pareto_types.py           # ParetoBundle, compute_pareto_bundle()
├── profiles.py               # 6 benannte ParetoProfile
├── whatif.py                 # What-if Engine ← NEU Sprint 2.5
├── tv_slots.py               # TV-Score
├── event_conflicts.py        # Event-Friction
└── revenue.py                # Gate-Revenue

tools/
└── demo_pareto.py            # End-to-End Demo-Skript

tests/
├── test_whatif.py            # 44 Tests ← NEU Sprint 2.5
├── test_sprint_2_4.py        # 13 Tests
├── test_fatigue_constraints.py # inkl. 2 Integration-Tests (AC-2.1.8/9)
└── ...

docs/
├── SPRINT_2_5_REVIEW.md      # aktuelles Review
├── SPRINT_2_4_REVIEW.md
└── ...
```

---

## Mögliche nächste Schritte (Sprint 2.6)

### Option A: What-if CLI / Web-UI
`tools/whatif_demo.py` als interaktives CLI, das alle 3 Szenario-Typen demonstriert und einen JSON-Report ausgibt. Oder eine HTML-Oberfläche die auf dem Pareto-Dashboard aufbaut.

### Option B: Integration mit Disruption Handler
`whatif_blackout()` nutzt aktuell eine eigene Reparatur-Logik. Sinnvoll: an `repair_regenerate.py` (Strategy B) andocken, um diesel be Code-Basis zu nutzen.

### Option C: Extended Team Analytics
`analyze_team_impact()` mit echtem Haversine-Travel statt Proxy. Pro Team: vollständiger Reisebericht vor/nach Modifikation.

### Option D: Stakeholder-Präsentation
Aktualisierung der PPTX (`docs/MLB_Optimizer_Sprint1_Review.pptx`) mit Sprint-2.x-Ergebnissen.

---

## Wichtige Zahlen (Seed 42)

| Metrik | Wert |
|---|---|
| Saison-Spiele | 2432 |
| Generator-Zeit | ~20s |
| AC-2.1.8 max | ≤ 13 ✓ |
| AC-2.1.9 max | ≤ 20 ✓ |
| Pareto-Punkte | ≥ 7 |
| What-if Latenz | < 2s |
| Unit-Tests (gesamt) | ~160+ |
