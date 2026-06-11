"""Sprint 5.4+ — Runden-/Pattern-basierte TTP-Formulierung.

Validiert die kompakte runden-indizierte Lösung: gültiger Plan (perfektes Matching je
Runde, matchup-komplett), löst n=4 OPTIMAL (wo das tag-indizierte MIP am Restricted-
Größenlimit scheitert), Runden→Tage-Mapping, Determinismus. Skippt ohne Gurobi-Lizenz.
"""
from __future__ import annotations

from collections import Counter

import pytest

from src.data_loader import load_teams

pytest.importorskip("gurobipy")

from src.ttp_rounds import (  # noqa: E402
    solve_ttp_rounds, rounds_to_days,
)
from src.greenfield_gurobi import GurobiUnavailable  # noqa: E402


def _teams(ids):
    return [t for t in load_teams() if t.id in ids]


def test_odd_team_count_rejected():
    with pytest.raises(ValueError):
        solve_ttp_rounds(_teams(("LAD", "SDP", "SFG")), games_per_pair=2)


def test_rounds_to_days_mapping():
    rg = [(0, "LAD", "SDP"), (1, "SFG", "LAD")]
    days = rounds_to_days(rg, day_gap=2, start_day=0)
    assert days == [(0, "LAD", "SDP"), (2, "SFG", "LAD")]


def test_rounds_solves_four_teams_optimal():
    teams = _teams(("LAD", "SDP", "SFG", "SEA"))
    try:
        r = solve_ttp_rounds(teams, games_per_pair=2, max_road_trip=3, time_limit_s=25)
    except GurobiUnavailable as exc:
        pytest.skip(f"Gurobi (Restricted) konnte nicht lösen: {exc}")
    assert r.status == "OPTIMAL"
    assert r.objective_km is not None and r.objective_km > 0
    assert r.n_rounds == 2 * (4 - 1)          # gpp·(n−1) = 6
    assert len(r.rounds) == 12

    # jede Runde = perfektes Matching (jedes Team genau 1×)
    by_round = {}
    for (rr, h, v) in r.rounds:
        by_round.setdefault(rr, []).append((h, v))
    all_ids = sorted(t.id for t in teams)
    for rr, gl in by_round.items():
        tin = sorted(t for (h, v) in gl for t in (h, v))
        assert tin == all_ids                 # alle Teams, genau einmal

    # Matchup-komplett: jede gerichtete Paarung exakt gpp//2 = 1×
    pairs = Counter((h, v) for (_, h, v) in r.rounds)
    assert all(c == 1 for c in pairs.values())
    home = Counter(h for (_, h, v) in r.rounds)
    for t in all_ids:
        assert home[t] == 3                   # hostet 3 (1 je Gegner)


def test_rounds_road_trip_limit_respected():
    teams = _teams(("LAD", "SDP", "SFG", "SEA"))
    L = 2
    try:
        r = solve_ttp_rounds(teams, games_per_pair=2, max_road_trip=L, time_limit_s=25)
    except GurobiUnavailable as exc:
        pytest.skip(f"Gurobi konnte nicht lösen: {exc}")
    # pro Team: nie mehr als L konsekutive Auswärtsrunden
    R = r.n_rounds
    for t in [tm.id for tm in teams]:
        away = []
        for rr in range(R):
            host = next((h for (gr, h, v) in r.rounds if gr == rr and (h == t or v == t)), None)
            away.append(0 if host == t else 1)
        run = mx = 0
        for a in away:
            run = run + 1 if a else 0
            mx = max(mx, run)
        assert mx <= L, f"{t}: {mx} konsekutive Auswärtsrunden > {L}"


def test_rounds_deterministic():
    teams = _teams(("LAD", "SDP", "SFG", "SEA"))
    try:
        a = solve_ttp_rounds(teams, games_per_pair=2, time_limit_s=25)
        b = solve_ttp_rounds(teams, games_per_pair=2, time_limit_s=25)
    except GurobiUnavailable as exc:
        pytest.skip(f"Gurobi konnte nicht lösen: {exc}")
    assert a.objective_km == pytest.approx(b.objective_km, rel=1e-6)
