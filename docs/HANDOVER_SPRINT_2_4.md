# Handover Sprint 2.4 — What-if Engine + Generator-Sliding-Window

**Datum:** 2026-05-25  
**Von:** Claude (Sprint 2.3b abgeschlossen)  
**Für:** Nächste Chat-Session (Sprint 2.4)

---

## TL;DR — wo wir stehen

Das Projekt ist ein MLB-Saisonoptimierungssystem für alle 30 Teams (162 Spiele, 186 Tage). Es liefert keine Punkt-Lösung, sondern eine **Pareto-Front** von 7+ nicht-dominierten Plänen über 8 Score-Dimensionen. Sprint 2.3b hat das vollständig implementiert und getestet.

**Alles grün:** 86/86 Sprint-2.3b-Tests, 95% Coverage, 2.22s Laufzeit (Budget: 300s).

Der nächste Sprint (2.4) hat **ein klar abgegrenztes, offenes AC** aus dem Charter das noch nicht fertig ist, plus neues Feature-Land.

---

## Repository-Struktur (Stand heute)

```
MLB Logistics Optimizer/
├── src/
│   ├── season.py              — Game/GameSeries/Season-Datenmodell
│   ├── data_loader.py         — Team-Stammdaten (30 Teams mit Koordinaten)
│   ├── loaders.py             — MLB-Stats-API-JSON-Loader (→ Season)
│   ├── generator.py           — CP-SAT Schedule-Generator (GeneratorConfig)
│   ├── generator_optimizer.py — SA Travel-Optimizer + optimize_pareto() [Sprint 2.3b]
│   ├── generator_constraints.py — Constraint-Helpers für den Generator
│   ├── column_generation.py   — Globaler HAP-Solver (solve_global_hap) [Sprint 2.3a]
│   ├── series_matching.py     — Phase-B Slot-Matching [Sprint 2.3a]
│   ├── two_phase_pacing.py    — Per-Team CP-SAT [Sprint 2.3a]
│   ├── pareto.py              — Pareto-Sampling-Engine [Sprint 2.3b] ← BUGFIX heute
│   ├── pareto_types.py        — ParetoBundle 8-Achsen-Datenmodell [Sprint 2.3b]
│   ├── profiles.py            — ParetoProfile + 6 Named Profiles [Sprint 2.3b]
│   ├── tv_slots.py            — TV-Slot-Score-Modell [Sprint 2.3b]
│   ├── event_conflicts.py     — Local-Event-Friction-Layer [Sprint 2.3b]
│   ├── revenue.py             — Attendance × Ticket-Preis-Revenue-Modell
│   ├── travel.py              — Haversine-Distanzberechnung
│   ├── player_fatigue.py      — max_consecutive_away_days, max_games_without_off_day
│   ├── disruption.py          — Disruption-Handler [Sprint 2.2]
│   ├── repair_*.py            — 3 Repair-Strategien [Sprint 2.2]
│   └── scoring.py / optimizer.py — Alter Prototyp (Sprint 0, weiterhin aktiv für ai_explainer.py)
├── data/
│   ├── teams.json             — 30 Teams (id, lat/lon, division, roof, etc.)
│   ├── mlb_schedule_2025.json — Echter MLB-2025-Schedule (2432 Spiele, via Stats API)
│   ├── mlb_schedule_2024.json — Echter MLB-2024-Schedule
│   ├── tv_slots.json          — TV-Slot-Werte, Marquee-Matchups, Pick-Probs
│   ├── local_events.json      — 40+ datierte Events 2026 inkl. Stadium-Bookings
│   └── revenue_model.json     — Gate-Revenue-Parameter (Sportico-kalibriert)
├── tests/
│   ├── conftest.py            — Session-Fixtures (teams, data_dir)
│   ├── test_sprint_2_3b.py    — 86 Tests, 95% Coverage ← HEUTE FERTIG
│   ├── test_sprint_2_3a.py    — 25 Tests (HAP-Solver, Phase B, AC-2.1.8/9)
│   ├── test_fatigue_constraints.py — 2x xfail(strict=True) ← NOCH OFFEN
│   └── test_*.py              — Sprint 2.1/2.2 Tests
├── dashboard/
│   ├── index.html             — Haupt-Dashboard (Travel-Optimizer)
│   └── pareto.html            — Interaktiver Pareto-Explorer (D3.js) [Sprint 2.3b]
└── docs/
    ├── SPRINT_2_3b_REVIEW.md  — Heute fertiggestellt
    ├── SPRINT_2_3a_REVIEW.md  — Sprint 2.3a Review
    ├── SPRINT_2_3_CHARTER.md  — Ursprünglicher Charter (noch relevant für AC-2.3.10/12)
    └── HANDOVER_SPRINT_2_3a.md — Altes Handover (jetzt DIESES Dokument ersetzt es)
```

---

## Was in Sprint 2.3b gebaut wurde (diese Session)

### Neue Module

**`src/tv_slots.py`** — TV-Slot-Score-Modell
- `TvSlotConfig.load()` liest `data/tv_slots.json` (9 Broadcaster, Marquee-Matchups, Pick-Probs)
- `game_tv_score(game, cfg)` → `GameTvScore` (slot_base × marquee_mult × pick_prob)
- `compute_tv_slot_score(season, cfg)` → `TvSlotReport` mit Gesamt-Score, Top-10, by_team/weekday
- Daypart-Heuristik: Sonntag=day, alle anderen=night (Limitation → Sprint 2.4)

**`src/pareto_types.py`** — 8-dimensionales ParetoBundle
- `ParetoBundle(frozen=True)`: travel_km, revenue_usd, fatigue_score, max_away_streak, off_day_variance, tv_slot_score, event_friction, constraint_violations
- `dominates(other)`: korrekte Pareto-Dominanz (revenue+tv negiert für "kleiner=besser")
- `compute_pareto_bundle(season, teams, events, tv_cfg, revenue_model)`: aggregiert alle 8 Dimensionen (~80ms für 2401 Spiele)

**`src/profiles.py`** (erweitert) — ParetoProfile-System
- `ParetoProfile(frozen=True)`: 8 Gewichte in km-Äquivalent-Einheiten
- `compute_energy(bundle)` → SA-Energie
- 6 Named Profiles: balanced, travel_min, revenue_max, player_friendly, tv_optimized, city_friendly
- `ParetoProfile.free(**weights)`: Custom-Profil, fehlende Gewichte aus "balanced"

**`src/generator_optimizer.py`** (erweitert) — `optimize_pareto()`
- Multi-Objective SA: gleiche SHIFT/SWAP-Moves wie `optimize_travel`, aber Energie = `profile.compute_energy(bundle)` in km-Äquivalent
- Inkrementeller State: 0.04ms/Iteration (statt 80ms Full-Recompute → 2000× speedup)
- Tracked: team_km_state, team_fat, entry_rev/tv/fric Arrays
- `_cv_from_state()`: O(num_teams) Constraint-Violations aus team_fat-State → in Energie eingebettet

**`src/pareto.py`** — Pareto-Sampling-Engine
- `sample_pareto_frontier(baseline_season, teams, cfg, master_seed, sa_iterations, ...)` → `ParetoFrontier`
- 6 Anker-Profile + N Interior-Profiles (Dirichlet-Mischung) → `filter_dominated()` → ≥7 Punkte
- Safety-Loop: bis zu 14 Extra-Runs wenn unter Minimum
- `ParetoFrontier.best_by(dimension)`: beste Punkt auf einer Dimension

**`dashboard/pareto.html`** — Interaktiver Pareto-Explorer
- D3.js v7 Scatter-Plot mit X/Y-Achsen-Selektor (alle 7 plotbaren Dimensionen)
- Pareto-Front-Linie, Hover-Tooltips (alle 8 Dim-Werte, grün=best/rot=worst), Click-to-Select-Sidebar
- Legende mit Toggle, Stats-Card, "Profil kopieren"-Button, embedded `window.PARETO_DATA`

**`tests/test_sprint_2_3b.py`** — 86 Tests, 95% Coverage

### Bugfixes in dieser Session

**Bug 1 (kritisch): `optimize_pareto()` — fehlende violations_penalty in SA-Energie**
- Symptom: SA akzeptierte Moves die AC-2.1.8/9 verletzten → alle Plans ungültig → 0 non-dominated
- Fix: `_energy_from_state()` enthält jetzt `+ profile.violations_penalty * _cv_from_state()`
- Datei: `src/generator_optimizer.py`

**Bug 2: `ParetoFrontier.best_by()` — AttributeError**
- Symptom: `AttributeError: 'ParetoPoint' object has no attribute 'travel_km'`
- Fix: Lambdas `lambda b: b.travel_km` → `lambda p: p.bundle.travel_km`
- Datei: `src/pareto.py`

**Bekannte Limitation (Doubleheader-Handling):**
- `_season_to_entries()` in `generator_optimizer.py` interpretiert DH-Spiele als 2-Tages-Serien
- Reale MLB-Schedules mit DH erzeugen phantom day-Überlappungen und falsche max_games_no_off-Werte
- Workaround für Tests: DH-Filterung (keep first game per (date, home, away))
- Fix für Sprint 2.4 geplant

---

## Hard Numbers (Baseline MLB-2025-Clean, 2401 Spiele)

| Metrik | Wert |
|---|---|
| `compute_pareto_bundle()` | ~80ms (mit cv-Check) |
| `optimize_pareto()` (3000 iter) | 0.13s, 0.04ms/iter, ~90 accepted |
| `sample_pareto_frontier()` (3000 iter, 4 interior) | **2.22s** / 18 runs |
| Non-dominated plans | **7** (AC-2.3.1: ≥7 ✅) |
| Budget | 300s (5 Min) |
| Coverage (4 Module) | **95%** |
| Baseline travel_km | 1.716M km |
| Baseline revenue_usd | $3.366B |
| Baseline tv_slot_score | 2858.8 (107 Marquee-Spiele) |

---

## Was in Sprint 2.4 zu tun ist

### AC-2.3.10 — NOCH OFFEN (aus Sprint 2.3-Charter, höchste Priorität)

**CP-SAT-Sliding-Window-Constraints in `src/generator.py`**

Das ist die einzige Sache aus dem Sprint-2.3-Charter die noch *nicht* grün ist.

**Kontext:** `tests/test_fatigue_constraints.py` hat 2 Tests mit `@pytest.mark.xfail(strict=True)`:
- `test_generator_ac218_consecutive_away` — prüft: generierter 30-Team-Plan hat max_consecutive_away_days ≤ 13
- `test_generator_ac219_off_day` — prüft: generierter 30-Team-Plan hat max_games_without_off_day ≤ 20

Aktuell schlägt der Sprint-2.1-Generator diese ACs (BAL hatte z.B. 109 Spiele ohne Off-Day). Der CP-SAT-Solver hat keine entsprechenden Constraints. Diese `xfail`-Marker sollen zu echten Tests werden.

**Was zu implementieren ist:** In `src/generator.py`, in der `generate()`-Funktion, nach dem CP-SAT-Encoding:

```python
# Pro Team t, für jedes 21-Tage-Fenster [d, d+20]:
# sum(plays[t][d:d+21]) <= 20  (AC-2.1.9: max 20 Spieltage in 21 Tagen)

# Pro Team t, für jedes 14-Tage-Fenster [d, d+13]:
# sum(away[t][d:d+14]) <= 13  (AC-2.1.8: max 13 konsekutive Auswärtstage)
```

**Challenge:** Der Generator arbeitet mit `IntervalVar` für Serien, nicht mit Per-Day-Booleans. Zwei Ansätze:
1. **Sliding-Window direkt auf Serien:** Für jede Gruppe von Serien die in einem Fenster liegen können, addiere ihre Längen und beachte min/max-Bounds. Komplex.
2. **Per-Day-Booleans nachträglich ableiten:** Nach CP-SAT-Encoding, für jedes Team, addiere alle Serien die Tag d belegen → `plays_on_day[t][d]`. Dann Sliding-Window-Constraint. Kann Solver-Zeit erhöhen.

**Performance-Budget:** AC-2.3.12 fordert Generator weiterhin ≤60s. Sprint-2.1-Baseline ist ~14s. Spielraum: 46s.

**Empfehlung:** Approach 2 (Per-Day-Booleans) ist sauberer, auch wenn etwas mehr CP-SAT-Variablen. Referenz: `src/generator_constraints.py` hat bereits verwandte Helper-Funktionen.

**Deliverables wenn fertig:**
- `tests/test_fatigue_constraints.py` — xfail-Marker entfernt, Tests grün
- `src/generator.py` — Sliding-Window-Constraints ergänzt
- Performance-Regression-Test: ≤60s

### Neue Sprint-2.4-Features (aus Charter-Abschnitt "Bewusst aufgeschoben")

**1. Daypart-Fix für TV-Slot-Score**  
Aktuell: Sonntag = "day", alles andere = "night" (Heuristik in `tv_slots.py`).  
Fix: MLB Stats API liefert `dayNight`-Feld pro Spiel. In `loaders.py` das Feld beim Laden übernehmen, in `Game`-Dataclass ergänzen, `_daypart_for_weekday()` durch echten Daypart ersetzen.  
Impact: Genauere TV-Scores, insbesondere für Sunday Night Baseball.

**2. Doubleheader-Fix in `_season_to_entries()`**  
Problem: DH-Spiele (2 Spiele am selben Tag, gleiche Paarung) werden als 2-Tages-Serie interpretiert. Fix: Serien nach *Tagen* gruppieren, nicht nach *Spielen*. SeriesEntry.length = Anzahl unique Tage (nicht Spiele).  
Impact: Reale MLB-Schedules können ohne DH-Filterung als Baseline für `optimize_pareto()` verwendet werden.

**3. demo_pareto.py — End-to-End-Demo-Skript**  
Das Sprint-2.3-Charter forderte ein `tools/demo_pareto.py` das:
- Eine vollständige Pareto-Frontier berechnet
- Die Ergebnisse als JSON in `window.PARETO_DATA` in `dashboard/pareto.html` einbettet (replace)
- Eine Summary-Ausgabe liefert
Derzeit enthält `dashboard/pareto.html` hardcoded Sample-Data. Das Demo-Skript würde es mit echten Daten befüllen.

**4. What-if Engine (Sprint 2.4 Kernfeature)**  
Ursprüngliches Sprint-2.4-Konzept aus `docs/SPRINT_2_CHARTER.md`:  
"Was passiert mit meiner Pareto-Front wenn ich Team X zwingt mehr Heim-Wochenend-Spiele zu haben?" → Re-Optimierung mit geänderten Constraints und Delta-Visualisierung der Frontier.

---

## Wichtige Architektur-Details für Sprint 2.4

### Team-ID-Mapping

Unsere internen IDs (aus `data/teams.json`): `NYY, BOS, LAD, SFG, ATL, ...` (30 Teams)  
Manche weichen von MLB-API-Codes ab: `KC` → `KCR`, `SD` → `SDP`, `SF` → `SFG`, `TB` → `TBR`, `WSH` → `WSN`  
Das Mapping ist in `src/loaders.py: MLB_ABBR_TO_CODE`.

### ParetoProfile-Energieskala

Alle Gewichte sind in **km-Äquivalent-Einheiten**:
- `w_travel = 1.0` (km/km)
- `w_revenue = -5e-7` (km/USD, negativ: mehr Revenue → weniger Energie)
- `w_fatigue = 20.0` (km/fatigue-point)
- `w_away_streak = 5000.0` (km/day)
- `w_off_day = 20_000_000.0` (km/variance — Varianz ist 0.00001-Bereich)
- `w_tv = -200.0` (km/tv-score-point, negativ)
- `w_friction = 500.0` (km/severity-point)
- `violations_penalty = 1_000_000_000.0` (faktisch unendlich)

SA start_temperature = 3_000_000.0 km-Äquivalent (matches typische Energie-Größenordnung).

### Doubleheader-Workaround für Tests

Für alle Tests die `optimize_pareto()` oder `sample_pareto_frontier()` mit echten MLB-Daten aufrufen:

```python
from src.loaders import load_mlb_schedule_json
from src.season import Season

raw = load_mlb_schedule_json(Path("data/mlb_schedule_2025.json"))
seen = set(); clean = []
for g in sorted(raw.games, key=lambda g: (g.date, g.game_pk)):
    key = (g.date, g.home, g.away)
    if key not in seen:
        seen.add(key)
        clean.append(g)
season = Season(2025, clean, raw.season_start, raw.season_end)
# → 2401 Spiele, 0 Overlaps, cv=0
```

Dieser Workaround ist in `tests/test_sprint_2_3b.py` als `_load_clean_2025_season()` bereits implementiert.

### Generator-Config-Muster

```python
from src.generator import GeneratorConfig
from datetime import date

cfg = GeneratorConfig(
    season=2026,
    season_start=date(2026, 3, 26),
    season_end=date(2026, 9, 28),
    all_star_break=(date(2026, 7, 13), date(2026, 7, 17)),  # optional
    max_solver_time_seconds=60.0,
    num_search_workers=1,   # WICHTIG: 1 für Determinismus (AC-2.1.11)
    random_seed=42,
)
```

### Volle Pareto-Frontier aufrufen

```python
from src.pareto import sample_pareto_frontier
from src.data_loader import load_teams

teams = load_teams()
# season = clean_2025_season (DH-gefiltert)

frontier = sample_pareto_frontier(
    baseline_season=season,
    teams=teams,
    cfg=cfg,
    master_seed=42,
    sa_iterations=3000,       # Production
    n_interior_points=4,      # 6 Anker + 4 Interior = 10 initial runs
    verbose=True,
)
# → ParetoFrontier mit ≥7 Punkten in ~2.2s
```

---

## Noch offene xfail-Tests

```
tests/test_fatigue_constraints.py::test_generator_ac218_consecutive_away  [xfail strict]
tests/test_fatigue_constraints.py::test_generator_ac219_off_day           [xfail strict]
```

Diese beiden Tests laufen einen vollständigen CP-SAT-Generator-Lauf (30 Teams, 162 Spiele) und prüfen dann `all_teams_pass_fatigue_constraints()`. Derzeit schlagen sie absichtlich fehl (`strict=True` bedeutet: wenn sie unerwartet grün werden, bricht die Suite ab — sauberes "Todo"-System).

**Sobald AC-2.3.10 implementiert ist:** xfail-Decorator entfernen, Tests sollten grün sein.

---

## Sprint-2.4-Vorschlag: Priorisierte Reihenfolge

1. **AC-2.3.10: Sliding-Window-Constraints** (höchste Priorität, technische Schuld)
   - `src/generator.py` erweitern
   - xfail-Tests grün machen
   - Performance-Regression prüfen (≤60s)

2. **Doubleheader-Fix** (entkoppelt die SA-Pipeline von manueller DH-Filterung)
   - `src/season.py`: `Game`-Dataclass um `day_night: str` Feld erweitern
   - `src/loaders.py`: `dayNight`-Feld aus API übernehmen
   - `src/generator_optimizer.py`: `_season_to_entries()` auf Day-Grouping umstellen
   - `src/tv_slots.py`: `_daypart_for_weekday()` durch `game.day_night` ersetzen

3. **`tools/demo_pareto.py`** (Charter-Anforderung, schnell umsetzbar)
   - Berechnet echte Frontier
   - Schreibt JSON-Data in `dashboard/pareto.html`
   - Gibt Summary auf stdout aus

4. **What-if Engine** (neues Feature)
   - Concept: Re-Optimierung mit geänderten Constraints (z.B. "NYY mindestens 20 Heim-Samstag-Spiele")
   - Delta-Visualisierung: wie verschiebt sich die Frontier?

---

## Handover-Checkliste

Folgendes ist sauber übergeben:

- [x] `src/pareto.py` — Bugfix `best_by()` Lambdas
- [x] `src/generator_optimizer.py` — Bugfix violations_penalty in SA-Energie
- [x] `tests/test_sprint_2_3b.py` — 86/86 grün, 95% Coverage
- [x] `docs/SPRINT_2_3b_REVIEW.md` — Vollständiger Review mit harten Zahlen
- [x] Memory aktualisiert (`memory/project_mlb_optimizer.md`)
- [ ] AC-2.3.10 (Sliding-Window-Constraints) → Sprint 2.4
- [ ] Doubleheader-Fix → Sprint 2.4
- [ ] `tools/demo_pareto.py` → Sprint 2.4
- [ ] `tests/test_fatigue_constraints.py` xfail → Sprint 2.4

---

## Quick-Start für nächste Session

```bash
# Alle Tests laufen (ohne slow):
cd "MLB Logistics Optimizer"
python3 -m pytest tests/ -v -m "not slow" --tb=short

# Sprint-2.3b-Tests (alle inkl. slow):
python3 -m pytest tests/test_sprint_2_3b.py -v --tb=short

# Aktuell noch offene xfail-Tests anzeigen:
python3 -m pytest tests/test_fatigue_constraints.py -v

# Quick-Sanity: Pareto-Frontier berechnen (2.2s)
python3 -c "
import sys; sys.path.insert(0, '.')
from src.loaders import load_mlb_schedule_json
from src.data_loader import load_teams
from src.season import Season
from src.generator import GeneratorConfig
from src.pareto import sample_pareto_frontier
from pathlib import Path
teams = load_teams()
raw = load_mlb_schedule_json(Path('data/mlb_schedule_2025.json'))
seen = set(); clean = []
for g in sorted(raw.games, key=lambda g:(g.date,g.game_pk)):
    k=(g.date,g.home,g.away)
    if k not in seen: seen.add(k); clean.append(g)
season = Season(2025, clean, raw.season_start, raw.season_end)
cfg = GeneratorConfig(2025, season.season_start, season.season_end)
f = sample_pareto_frontier(season, teams, cfg, master_seed=42,
    sa_iterations=3000, n_interior_points=4, verbose=True)
print(f'Non-dominated: {f.n_non_dominated}, wall_time: {f.total_wall_time_s:.2f}s')
"
```
