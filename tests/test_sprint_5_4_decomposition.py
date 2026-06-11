"""Sprint 5.4+ — Runden-/Fenster-Dekomposition (Rolling-Horizon).

Validiert: gültiger, matchup-kompletter Plan; nie schlechter als der Bootstrap;
skaliert auf Instanzen, die der monolithische Solver (Restricted License) nicht mehr
fasst. Skippt sauber ohne lösbare Gurobi-Lizenz.
"""
from __future__ import annotations

from collections import Counter

import pytest

from src.data_loader import load_teams

pytest.importorskip("gurobipy")

from src.greenfield_gurobi import round_robin_instance, GurobiUnavailable  # noqa: E402
from src.greenfield_decomp import solve_greenfield_windowed  # noqa: E402


def _inst(team_ids, gpp=2, days=20, K=6):
    teams = [t for t in load_teams() if t.id in team_ids]
    return round_robin_instance(teams, games_per_pair=gpp, n_days=days, max_consecutive=K)


def _assert_valid(games, n_teams, gpp):
    assert len(games) == (n_teams * (n_teams - 1) // 2) * gpp
    for d in {g[0] for g in games}:
        on = [t for (gd, h, v) in games if gd == d for t in (h, v)]
        assert max(Counter(on).values()) == 1   # kein Doppel-Booking
    # jede gerichtete Paarung exakt gpp//2 mal (Heim-Quote der Round-Robin-Instanz)
    pairs = Counter((h, v) for (_, h, v) in games)
    assert all(c == gpp // 2 for c in pairs.values())


def test_windowed_valid_and_not_worse():
    inst = _inst(("LAD", "SDP", "SFG"), gpp=4, days=20, K=6)
    try:
        w = solve_greenfield_windowed(inst, window_days=7, passes=2, window_time_s=6)
    except GurobiUnavailable as exc:
        pytest.skip(f"Gurobi konnte nicht lösen: {exc}")
    _assert_valid(w.games, 3, 4)
    assert w.objective_km <= w.bootstrap_km + 1e-6


def test_windowed_scales_to_four_teams():
    # 4 Teams: der monolithische Solver sprengt das Restricted-Größenlimit; die
    # Fenster-Dekomposition liefert trotzdem einen gültigen Plan.
    inst = _inst(("LAD", "SDP", "SFG", "SEA"), gpp=2, days=20, K=6)
    try:
        w = solve_greenfield_windowed(inst, window_days=6, passes=2, window_time_s=6)
    except GurobiUnavailable as exc:
        pytest.skip(f"Gurobi konnte nicht lösen: {exc}")
    _assert_valid(w.games, 4, 2)
    home = Counter(h for (_, h, v) in w.games)
    for t in ("LAD", "SDP", "SFG", "SEA"):
        assert home[t] == 3       # jedes Team hostet 3 (1 je Gegner)


def test_windowed_deterministic():
    inst = _inst(("LAD", "SDP", "SFG"), gpp=2, days=16, K=5)
    try:
        a = solve_greenfield_windowed(inst, window_days=6, passes=1, window_time_s=5)
        b = solve_greenfield_windowed(inst, window_days=6, passes=1, window_time_s=5)
    except GurobiUnavailable as exc:
        pytest.skip(f"Gurobi konnte nicht lösen: {exc}")
    assert a.objective_km == pytest.approx(b.objective_km, rel=1e-6)
