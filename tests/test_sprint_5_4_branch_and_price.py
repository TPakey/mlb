"""Sprint 5.4+ — Branch-and-Price / Column Generation.

Validiert die Dekomposition auf reduzierten Instanzen: gültiger, matchup-kompletter,
konsistenter Plan; nie schlechter als der Bootstrap; mit Seed erreicht der integer
Master das (mit echtem Reisemodell gemessene) monolithische Optimum. Skippt sauber
ohne lösbare Gurobi-Lizenz.
"""
from __future__ import annotations

from collections import Counter

import pytest

from src.data_loader import load_teams

pytest.importorskip("gurobipy")

from src.greenfield_gurobi import (  # noqa: E402
    round_robin_instance, solve_greenfield, GurobiUnavailable,
)
from src.branch_and_price import (  # noqa: E402
    branch_and_price, branch_and_price_optimal, greedy_feasible_schedule,
    decompose_to_columns, _column_cost,
)


def _inst():
    teams = [t for t in load_teams() if t.id in ("NYY", "BOS", "TBR")]
    return round_robin_instance(teams, games_per_pair=2, n_days=9, max_consecutive=4)


def _assert_valid_schedule(games, ids, games_per_pair=2):
    # genau (#Paare × games_per_pair) Spiele
    assert len(games) == 3 * games_per_pair
    # ≤1 Spiel/Team/Tag
    for d in {g[0] for g in games}:
        on_day = [t for (gd, h, v) in games if gd == d for t in (h, v)]
        assert max(Counter(on_day).values()) == 1
    # jede gerichtete Paarung genau 1× (round-robin home-split)
    pairs = [(h, v) for (_, h, v) in games]
    assert len(set(pairs)) == len(pairs)


def test_greedy_bootstrap_is_feasible():
    inst = _inst()
    sched = greedy_feasible_schedule(inst)
    _assert_valid_schedule(sched, inst.ids)


def test_decompose_cost_matches():
    inst = _inst()
    tbi = {t.id: t for t in inst.teams}
    sched = greedy_feasible_schedule(inst)
    cols = decompose_to_columns(sched, inst, tbi)
    # jede Spalte enthält genau die Spiele ihres Teams (4 = 2 Gegner × 2)
    for t, col in cols.items():
        assert len(col.events) == 4
        assert col.cost_km == _column_cost(t, col.events, tbi)


def test_bnp_produces_valid_schedule():
    inst = _inst()
    try:
        res = branch_and_price(inst, max_cg_iter=4, pricing_time_s=6)
    except GurobiUnavailable as exc:
        pytest.skip(f"Gurobi (Restricted) konnte nicht lösen: {exc}")
    assert res.objective_km is not None
    _assert_valid_schedule(res.games, inst.ids)
    # nie schlechter als der Bootstrap
    assert res.objective_km <= res.bootstrap_km + 1e-6
    assert res.n_columns >= 3


def test_bnp_seeded_reaches_monolithic_optimum():
    inst = _inst()
    try:
        mono = solve_greenfield(inst, time_limit_s=25)
        res = branch_and_price(inst, max_cg_iter=3, pricing_time_s=6,
                               seed_schedules=[mono.games])
    except GurobiUnavailable as exc:
        pytest.skip(f"Gurobi (Restricted) konnte nicht lösen: {exc}")
    assert mono.objective_km is not None and res.objective_km is not None
    # gleiches (echtes) Reisemodell → B&P erreicht das monolithische Optimum
    assert res.objective_km <= mono.objective_km + 1.0


def test_bnp_tree_produces_valid_and_not_worse():
    inst = _inst()
    try:
        res = branch_and_price_optimal(inst, max_nodes=20, cg_iter_per_node=3,
                                       pricing_time_s=5, time_limit_s=40)
    except GurobiUnavailable as exc:
        pytest.skip(f"Gurobi (Restricted) konnte nicht lösen: {exc}")
    assert res.objective_km is not None
    _assert_valid_schedule(res.games, inst.ids)
    assert res.objective_km <= res.bootstrap_km + 1e-6


def test_bnp_tree_seeded_reaches_optimum():
    inst = _inst()
    try:
        mono = solve_greenfield(inst, time_limit_s=25)
        res = branch_and_price_optimal(inst, max_nodes=20, cg_iter_per_node=3,
                                       pricing_time_s=5, time_limit_s=40,
                                       seed_schedules=[mono.games])
    except GurobiUnavailable as exc:
        pytest.skip(f"Gurobi (Restricted) konnte nicht lösen: {exc}")
    assert res.objective_km <= mono.objective_km + 1.0
