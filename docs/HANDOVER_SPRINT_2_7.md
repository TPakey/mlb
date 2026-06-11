# Handover Sprint 2.7

**Datum:** 2026-05-26
**Von:** Claude (Sprint 2.6 abgeschlossen)
**Für:** Nächste Chat-Session

---

## TL;DR

Sprint 2.6 ist abgeschlossen. Das **What-if CLI Demo-Skript** (`tools/whatif_demo.py`)
ist vollständig implementiert, getestet (40/40 Unit-Tests, 0.64s) und dokumentiert.

Das System kann jetzt:
1. **Vollständige Saisonpläne generieren** (CP-SAT + SA, ~20s, AC-2.1.8/9-konform)
2. **Pareto-Front** über 8 Dimensionen berechnen
3. **What-if-Szenarien** in < 2s analysieren (Force Serie, Blackout, Plan-Vergleich)
4. **CLI-Demo** aller 3 Szenarien mit JSON-Export (Sprint 2.6 ← NEU)

---

## Was in Sprint 2.6 gebaut wurde

### `tools/whatif_demo.py` — CLI-Demo für alle 3 What-if-Szenario-Typen

```bash
# Alle Szenarien (Standard)
python -m tools.whatif_demo

# Einzelne Szenarien
python -m tools.whatif_demo --scenario force      # NYY@BOS am 4. Juli
python -m tools.whatif_demo --scenario blackout   # HOU Konzert-Blackout
python -m tools.whatif_demo --scenario compare    # Balanced vs. Travel-Optimiert

# Export
python -m tools.whatif_demo --json-out output/report.json
```

**3 Demo-Szenarien:**
- **Force Series:** NYY@BOS am 4. Juli 2026 (Independence Day Klassiker)
- **Venue Blackout:** HOU Minute Maid Park, 15.–16. Aug 2026 (Konzert)
- **Plan-Vergleich:** Balanced vs. Travel-optimierter Pareto-Plan

**JSON-Output:**
```json
{
  "meta": { "season": 2026, "seed": 42, "sprint": "2.6", ... },
  "scenarios": [
    { "scenario": "force_nyyatbos_jul4", "feasible": true, "n_better": 3, ... },
    { "scenario": "blackout_hou_aug15", ... },
    { "scenario": "compare_balanced_vs_travel", ... }
  ]
}
```

### `tests/test_whatif_demo.py` — 40 Tests, 0.64s

---

## Vollständige Datei-Struktur (Stand Sprint 2.6)

```
src/
├── generator.py              # CP-SAT + SA (enforce_fatigue_constraints=True)
├── generator_optimizer.py    # SA + Doubleheader-Fix
├── player_fatigue.py         # AC-2.1.8/9 Validierung
├── pareto.py                 # sample_pareto_frontier()
├── pareto_types.py           # ParetoBundle, compute_pareto_bundle()
├── profiles.py               # 6 benannte ParetoProfile
├── whatif.py                 # What-if Engine (Sprint 2.5)
├── tv_slots.py               # TV-Score
├── event_conflicts.py        # Event-Friction
└── revenue.py                # Gate-Revenue

tools/
├── demo_pareto.py            # Pareto-Demo (Sprint 2.4)
└── whatif_demo.py            # What-if-Demo ← NEU Sprint 2.6

tests/
├── test_whatif_demo.py       # 40 Tests ← NEU Sprint 2.6
├── test_whatif.py            # 44 Tests (Sprint 2.5)
├── test_sprint_2_4.py        # 13 Tests
├── test_fatigue_constraints.py
└── ...

docs/
├── SPRINT_2_6_REVIEW.md      # aktuelles Review
├── SPRINT_2_5_REVIEW.md
├── GESAMTBERICHT_FUER_REVIEW.md  # Gesamtbericht für externes Review (Sprint 2.5)
└── ...
```

---

## Test-Gesamtübersicht (Stand Sprint 2.6)

| Datei | Tests | Zeit |
|---|---|---|
| `test_whatif_demo.py` | 40 | 0.64s |
| `test_whatif.py` | 44 | 0.56s |
| `test_sprint_2_4.py` | 13 | 0.58s |
| `test_sprint_2_3b.py` | 86 | ~5s |
| `test_sprint_2_3a.py` | 25 | ~33s |
| `test_fatigue_constraints.py` | inkl. 2 xfail (Sprint 2.3a) | — |
| **Gesamt (fast)** | **~200+** | **< 10s (ohne 2.3a)** |

---

## Mögliche nächste Schritte (Sprint 2.7)

### Option A: What-if Web-Interface
Eine HTML-Oberfläche, die auf dem Pareto-Dashboard (`dashboard/pareto.html`)
aufbaut und What-if-Szenarien interaktiv per Formular ermöglicht. Nutzt
`WhatIfResult.to_dict()` für den JSON-Transport.

### Option B: REST-API
`tools/api.py` mit FastAPI/Flask: POST-Endpunkte für alle 3 What-if-Typen.
MLB-IT könnte das direkt in ihre Systeme integrieren.
Beispiel: `POST /whatif/force-series` → JSON-Response in < 2s.

### Option C: Home-Stand-Constraint (AC-2.1.X)
Analoge Constraint zu AC-2.1.8: maximal N konsekutive Heimspiele pro Team.
Aktuell gibt es keine Obergrenze für Heimserien. CBA-Relevanz mittel.

### Option D: Dashboard-Integration
`dashboard/pareto.html` um einen "What-if"-Bereich erweitern:
Dropdown für Szenario-Typ, Datum-Picker, Delta-Anzeige direkt im Browser.

### Option E: Stakeholder-Präsentation aktualisieren
`docs/MLB_Optimizer_Sprint1_Review.pptx` ist von Sprint 1 und kennt noch
keine CP-SAT+SA-Pipeline, Pareto-Front, What-if Engine oder AC-2.1.8/9.
Update mit Sprint-2.x-Ergebnissen für MLB-Präsentation.

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
| Unit-Tests (gesamt) | ~200+ |
| Demo-Skripte | 2 (demo_pareto.py + whatif_demo.py) |
