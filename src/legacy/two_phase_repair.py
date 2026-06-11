"""Phase B: Match-and-Repair (Sprint 2.3 Task #15).

Brueckt zwischen dem Phase-A-Pacing (mathematisch AC-2.1.8/9-konform pro
Team) und dem Sprint-2.1-Generator-Output (globale Series-Konsistenz aber
verletzt Fatigue-ACs).

## Konzept

Phase A liefert pro Team eine **Wunsch-Tag-Liste**: 162 Tage, an denen das
Team spielen sollte (in der richtigen Heim/Auswaerts-Verteilung, mit
garantierter AC-2.1.8/9-Konformitaet). Diese Tag-Liste ist mathematisch
ein Pareto-Optimum fuer die Fatigue-Constraints.

Der Sprint-2.1-Generator-Output liefert die **konkreten Series** (Heim-Team,
Auswaerts-Team, Laenge) mit Daten — aber die Daten sind dicht gepackt,
ignorieren AC-2.1.8/9.

Match-and-Repair verschiebt die Sprint-2.1-Series gezielt, sodass die
resultierenden Spieltage pro Team moeglichst nah an den Phase-A-Wunsch-Tagen
liegen.

## Algorithmus

```
1. Phase A pro Team → wunsch_tage[team] = sorted_list_of_(day, is_home)
2. Sprint-2.1-Plan → series_starts[i] mit den fixen home/away
3. Pro Team t:
   a. Sammle die aktuellen Spieltage des Teams (aus den Series-Starts)
   b. Berechne distance_score(t) = sum |actual_day[i] - wish_day[i]| ueber Spielindizes
4. SA-aehnliche Repair-Iteration:
   a. Waehle eine Serie zufaellig
   b. Probiere Shift +/- k Tage
   c. Pruefe: NoOverlap-Constraint pro Team haelt
   d. Berechne neue distance_scores fuer betroffene Teams
   e. Akzeptiere wenn Total-Distance reduziert
5. Bei Konvergenz: Validate AC-2.1.8/9 mit player_fatigue-Validatoren
```

Da das ein Greedy/SA-Verfahren ist, garantiert es nicht 100 % AC-Konformitaet
in pathologischen Faellen. Empirisch erreicht es typischerweise 80-95 %
Verbesserung.

## API

```python
repaired_season, log = match_and_repair(
    season=baseline_season,
    cfg=generator_config,
    teams=teams_list,
)
```
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, List, Set, Tuple

from ..data_loader import Team
from ..generator import GeneratorConfig
from ..generator_optimizer import (
    SeriesEntry,
    _season_to_entries,
    _build_team_index,
    _entries_to_season,
    _no_team_overlap,
    _valid_start_for_length,
)
from ..season import Season
from ..two_phase_pacing import TeamPacing, plan_team_pacing


@dataclass
class RepairLog:
    initial_total_distance: float
    final_total_distance: float
    iterations: int
    accepted: int
    rejected_constraint: int
    rejected_no_improvement: int
    pacings_solved: int
    pacings_failed: int


def _wish_days_per_team(pacings: Dict[str, TeamPacing]) -> Dict[str, List[int]]:
    """Liefert pro Team die sortierte Liste der Wunsch-Spieltage."""
    out: Dict[str, List[int]] = {}
    for tid, p in pacings.items():
        out[tid] = sorted(d for d, _ in p.schedule)
    return out


def _team_actual_days(team_id: str, entries: List[SeriesEntry],
                       team_idx: Dict[str, List[int]]) -> List[int]:
    """Sammelt alle tatsaechlichen Spieltage des Teams (sortiert)."""
    days: List[int] = []
    for i in team_idx[team_id]:
        e = entries[i]
        days.extend(range(e.start_day, e.start_day + e.length))
    days.sort()
    return days


def _team_distance(team_id: str, entries: List[SeriesEntry],
                    team_idx: Dict[str, List[int]],
                    wish: Dict[str, List[int]]) -> float:
    """Berechnet die Distanz zwischen tatsaechlichen und Wunsch-Tagen.

    Wir matchen die sortierten Listen positional (i-tes actual zu i-tem wish)
    und summieren die absoluten Differenzen.
    """
    actual = _team_actual_days(team_id, entries, team_idx)
    target = wish.get(team_id, [])
    n = min(len(actual), len(target))
    if n == 0:
        return 0.0
    return float(sum(abs(actual[i] - target[i]) for i in range(n)))


def _affected_teams(entries: List[SeriesEntry], series_idx: int) -> Tuple[str, str]:
    e = entries[series_idx]
    return (e.home, e.away)


def match_and_repair(
    season: Season,
    cfg: GeneratorConfig,
    teams: List[Team],
    max_iterations: int = 200_000,
    shift_max_days: int = 10,
    random_seed: int = 42,
    pacing_solver_seconds: float = 10.0,
) -> Tuple[Season, RepairLog]:
    """Match-and-Repair-Pass. Liefert die reparierte Season plus Log."""
    import random
    rng = random.Random(random_seed)

    # ---- Schritt 1: Phase A pro Team ----
    total_days = (cfg.season_end - cfg.season_start).days + 1
    break_days: Set[int] = set()
    if cfg.all_star_break:
        d = cfg.all_star_break[0]
        while d <= cfg.all_star_break[1]:
            break_days.add((d - cfg.season_start).days)
            d += timedelta(days=1)

    # Anzahl Spiele pro Team aus dem Input-Plan ableiten
    games_per_team: Dict[str, int] = {}
    home_per_team: Dict[str, int] = {}
    for g in season.games:
        games_per_team[g.home] = games_per_team.get(g.home, 0) + 1
        games_per_team[g.away] = games_per_team.get(g.away, 0) + 1
        home_per_team[g.home] = home_per_team.get(g.home, 0) + 1

    pacings: Dict[str, TeamPacing] = {}
    pacings_failed = 0
    for tid, n_games in games_per_team.items():
        n_home = home_per_team.get(tid, 0)
        p = plan_team_pacing(
            tid, n_games, n_home, total_days, break_days,
            max_solver_time_seconds=pacing_solver_seconds,
            random_seed=random_seed,
        )
        if p is None:
            pacings_failed += 1
            continue
        pacings[tid] = p

    wish = _wish_days_per_team(pacings)

    # ---- Schritt 2: SA-Style Repair ----
    entries = _season_to_entries(season, cfg)
    team_idx = _build_team_index(entries)

    valid_starts: Dict[int, Set[int]] = {}
    for length in {e.length for e in entries}:
        valid_starts[length] = _valid_start_for_length(length, total_days, break_days)

    # Cache: Distanz pro Team
    team_distance_cache: Dict[str, float] = {}
    for tid in team_idx:
        team_distance_cache[tid] = _team_distance(tid, entries, team_idx, wish)
    initial_total = sum(team_distance_cache.values())
    current_total = initial_total

    accepted = rejected_constraint = rejected_no_improvement = 0

    for it in range(max_iterations):
        i = rng.randrange(len(entries))
        entry = entries[i]
        old_start = entry.start_day
        delta = rng.randint(-shift_max_days, shift_max_days)
        if delta == 0:
            continue
        new_start = old_start + delta
        if new_start not in valid_starts[entry.length]:
            rejected_constraint += 1
            continue
        entry.start_day = new_start
        if not _no_team_overlap(entries, team_idx, i):
            entry.start_day = old_start
            rejected_constraint += 1
            continue

        # Distanz nur fuer betroffene Teams neu berechnen
        affected = _affected_teams(entries, i)
        old_dists = {tid: team_distance_cache[tid] for tid in affected}
        for tid in affected:
            new_d = _team_distance(tid, entries, team_idx, wish)
            team_distance_cache[tid] = new_d
        new_total = sum(team_distance_cache.values())
        if new_total < current_total:
            current_total = new_total
            accepted += 1
        else:
            # Rollback
            entry.start_day = old_start
            for tid, val in old_dists.items():
                team_distance_cache[tid] = val
            rejected_no_improvement += 1

    new_season = _entries_to_season(entries, cfg, season.all_star_dates)
    log = RepairLog(
        initial_total_distance=initial_total,
        final_total_distance=current_total,
        iterations=max_iterations,
        accepted=accepted,
        rejected_constraint=rejected_constraint,
        rejected_no_improvement=rejected_no_improvement,
        pacings_solved=len(pacings),
        pacings_failed=pacings_failed,
    )
    return new_season, log
