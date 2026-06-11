"""Regressionstests fuer die QA-Audit-Fixes (docs/QA_AUDIT_2026-05-29.md).

Deckt Befunde ab, die zuvor keinen direkten Test hatten:
- Q3: optimize_travel pflegt km inkrementell — das Ergebnis muss deterministisch
  und bit-konsistent zur Voll-Neuberechnung (_total_km) bleiben.
- Q1: Doubleheader-Zaehlung ist in test_fatigue_constraints.py abgedeckt.
- Q10: Soundness der AC-2.1.8-Gap-Formulierung (_add_ac_2_1_8_gap_constraints).
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from ortools.sat.python import cp_model

from src.season import Game, Season
from src.generator import GeneratorConfig, _add_ac_2_1_8_gap_constraints
from src.generator_optimizer import (
    optimize_travel,
    _total_km,
    _season_to_entries,
    _build_team_index,
    OptimizerConfig,
)


def _synthetic_season(teams):
    ids = [t.id for t in teams[:6]]
    base = date(2026, 4, 1)
    schedule = [
        (0, ids[0], ids[1]), (3, ids[2], ids[3]), (6, ids[4], ids[5]),
        (10, ids[1], ids[2]), (14, ids[3], ids[4]), (18, ids[5], ids[0]),
        (24, ids[0], ids[2]), (28, ids[4], ids[1]), (32, ids[3], ids[5]),
    ]
    games = []
    pk = 1
    for start, home, away in schedule:
        for off in range(2):
            games.append(Game(game_pk=pk, date=base + timedelta(days=start + off),
                              home=home, away=away, venue=home,
                              doubleheader_seq=0, game_type="R"))
            pk += 1
    season = Season(season=2026, games=sorted(games, key=lambda g: (g.date, g.game_pk)),
                    season_start=base, season_end=base + timedelta(days=60))
    cfg = GeneratorConfig(season=2026, season_start=base,
                          season_end=base + timedelta(days=60),
                          enforce_fatigue_constraints=False)
    return season, cfg


def test_optimize_travel_incremental_km_matches_full_recompute(teams):
    """QA Q3: final_km (inkrementell gepflegt) == _total_km von Grund auf."""
    season, cfg = _synthetic_season(teams)
    teams_by_id = {t.id: t for t in teams}
    opt, log = optimize_travel(season, teams, cfg, OptimizerConfig(iterations=800, seed=42))

    entries = _season_to_entries(opt, cfg)
    team_idx = _build_team_index(entries)
    fresh = _total_km(entries, team_idx, teams_by_id)
    assert abs(fresh - log.final_km) < 1e-9


def test_optimize_travel_is_deterministic(teams):
    """QA Q3: gleicher Seed -> bit-identisches Ergebnis (Bit-Identitaets-Versprechen)."""
    season, cfg = _synthetic_season(teams)
    _, log1 = optimize_travel(season, teams, cfg, OptimizerConfig(iterations=800, seed=42))
    _, log2 = optimize_travel(season, teams, cfg, OptimizerConfig(iterations=800, seed=42))
    assert log1.final_km == log2.final_km


def test_optimize_travel_improves_or_holds(teams):
    """Sanity: die SA verschlechtert die km nie gegenueber dem Start."""
    season, cfg = _synthetic_season(teams)
    _, log = optimize_travel(season, teams, cfg, OptimizerConfig(iterations=800, seed=42))
    assert log.final_km <= log.initial_km + 1e-9


# ====================================================================
# Q10: Soundness der AC-2.1.8-Gap-Formulierung
# ====================================================================
#
# Die Formulierung `_add_ac_2_1_8_gap_constraints` ist im Produktionspfad
# bewusst NICHT verdrahtet (intermittierende Tractability mit All-Star-Break,
# siehe docs/QA_AUDIT_2026-05-29.md Q10 + docs/REFACTOR_BACKLOG.md). Diese Tests
# sichern aber ihre KORREKTHEIT ab: jede Loesung, die die Constraints erfuellt,
# muss eine maximale Road-Trip-Spanne <= 13 haben. Damit ist die Formulierung
# fuer den dokumentierten Folge-Sprint als verifiziert-sound hinterlegt.

def _max_away_span(home_days, away_days):
    """Unabhaengiges Orakel: laengste Road-Trip-Spanne (Off-Days inklusive)."""
    is_home = set(home_days)
    is_away = set(away_days)
    play = sorted(is_home | is_away)
    worst = 0
    start = end = None
    for d in play:
        if d in is_away:
            if start is None:
                start = d
            end = d
        elif d in is_home:
            if start is not None:
                worst = max(worst, end - start + 1)
                start = end = None
    if start is not None:
        worst = max(worst, end - start + 1)
    return worst


def _solve_one_team(n_home, n_away, total_days, seed):
    """Baut ein Ein-Team-Modell mit der Gap-Constraint und loest es."""
    m = cp_model.CpModel()
    rng = random.Random(seed)
    home, away, intervals = [], [], []

    def add(L, store):
        valid = list(range(total_days - L + 1))
        if not valid:
            return False
        s = m.NewIntVarFromDomain(cp_model.Domain.FromValues(valid), f"s{len(intervals)}")
        e = m.NewIntVar(0, total_days, f"e{len(intervals)}")
        m.Add(e == s + L)
        intervals.append(m.NewIntervalVar(s, L, e, f"iv{len(intervals)}"))
        store.append((s, e, L))
        return True

    for _ in range(n_home):
        if not add(rng.choice([2, 3, 4]), home):
            return None
    for _ in range(n_away):
        if not add(rng.choice([2, 3, 4]), away):
            return None
    m.AddNoOverlap(intervals)
    _add_ac_2_1_8_gap_constraints(m, {"T": home}, total_days)

    sol = cp_model.CpSolver()
    sol.parameters.max_time_in_seconds = 5
    sol.parameters.random_seed = seed
    st = sol.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return "infeasible"
    hd, ad = set(), set()
    for (s, e, L) in home:
        for o in range(L):
            hd.add(sol.Value(s) + o)
    for (s, e, L) in away:
        for o in range(L):
            ad.add(sol.Value(s) + o)
    return _max_away_span(hd, ad)


def test_ac218_gap_formulation_is_sound():
    """QA Q10: keine die Gap-Constraint erfuellende Loesung darf > 13 sein.

    Orakel-Test ueber Zufallsinstanzen (vgl. die 315-Faelle-Verifikation im
    QA-Audit; hier eine kompakte, schnelle Teilmenge fuer die CI).
    """
    random.seed(0)
    feasible = 0
    for _ in range(40):
        nh = random.randint(2, 5)
        na = random.randint(2, 6)
        total_days = random.randint(30, 55)
        seed = random.randint(0, 10**6)
        res = _solve_one_team(nh, na, total_days, seed)
        if isinstance(res, int):
            feasible += 1
            assert res <= 13, f"Gap-Formulierung UNSOUND: worst_away={res}"
    assert feasible > 0, "kein einziger Fall feasible — Test degeneriert"
