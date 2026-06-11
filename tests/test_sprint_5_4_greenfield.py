"""Sprint 5.4 — B3 Balanced-Schedule-Format + green-field Gurobi-Solver.

Die Gurobi-Tests laufen unter der Restricted License (kleine Instanzen) und
SKIPPEN sauber, wenn gurobipy fehlt oder das Größenlimit greift — so bleibt die
Suite ohne akademische Lizenz grün, und mit Jonas' Key löst derselbe Code große
Instanzen.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.data_loader import load_teams
from src.datasources.local_file import LocalFileAdapter
from src.balanced_schedule import (
    category, derive_matchup_matrix, canonicalize_matrix, validate_format,
    round_robin_matrix, format_summary, EXPECTED_TOTAL,
)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


@pytest.fixture(scope="module")
def teams():
    return load_teams()


# ---------- B3: Balanced-Schedule-Format ----------

def test_format_summary_sums_to_162():
    s = format_summary()
    cats = s["categories"]
    assert (cats["intra-div"]["sum"] + cats["intra-league"]["sum"]
            + cats["interleague"]["sum"]) == EXPECTED_TOTAL


def test_category(teams):
    tbi = {t.id: t for t in teams}
    assert category(tbi["NYY"], tbi["BOS"]) == "intra-div"        # AL East
    assert category(tbi["NYY"], tbi["HOU"]) == "intra-league"     # AL, diff div
    assert category(tbi["NYY"], tbi["LAD"]) == "interleague"      # AL vs NL


def test_matchup_matrix_symmetric(teams):
    s = LocalFileAdapter(base_dir=DATA).fetch_season_schedule(2024)
    m = derive_matchup_matrix(s, teams)
    for a in m:
        for b in m[a]:
            assert m[a][b] == m[b][a]


def test_real_2024_is_balanced_format(teams):
    s = LocalFileAdapter(base_dir=DATA).fetch_season_schedule(2024)
    viols = validate_format(s, teams)
    assert viols == [], f"2024 sollte sauberes Format sein: {[v.detail for v in viols]}"


def test_canonicalize_restores_totals(teams):
    s = LocalFileAdapter(base_dir=DATA).fetch_season_schedule(2024)
    tbi = {t.id: t for t in teams}
    cm = canonicalize_matrix(derive_matchup_matrix(s, teams), tbi)
    for a, row in cm.items():
        assert abs(sum(row.values()) - EXPECTED_TOTAL) <= 1


def test_round_robin_matrix():
    m = round_robin_matrix(["A", "B", "C"], 2)
    assert m["A"]["B"] == 2 and m["B"]["A"] == 2
    assert "A" not in m["A"]


# ---------- Green-field Gurobi-Solver ----------

gp = pytest.importorskip("gurobipy")  # skip ganzes Modul, wenn gurobipy fehlt

from src.greenfield_gurobi import (  # noqa: E402
    gurobi_status, round_robin_instance, solve_greenfield, GurobiUnavailable,
    directed_quota_from_matchup,
)


def test_gurobi_status():
    st = gurobi_status()
    assert st["available"] is True
    assert "license_source" in st


def test_directed_quota_split():
    sym = {"A": {"B": 4, "C": 3}, "B": {"A": 4, "C": 2}, "C": {"A": 3, "B": 2}}
    hq = directed_quota_from_matchup(sym)
    # Summe Heim(i,j)+Heim(j,i) == Gesamtspiele/Paar
    assert hq["A"]["B"] + hq["B"]["A"] == 4
    assert hq["A"]["C"] + hq["C"]["A"] == 3
    assert hq["B"]["C"] + hq["C"]["B"] == 2


def test_greenfield_solves_reduced_instance(teams):
    sub = [t for t in teams if t.id in ("NYY", "BOS", "TBR")]
    inst = round_robin_instance(sub, games_per_pair=2, n_days=9, max_consecutive=4)
    try:
        res = solve_greenfield(inst, time_limit_s=20)
    except GurobiUnavailable as exc:
        pytest.skip(f"Gurobi (Restricted) konnte nicht lösen: {exc}")
    assert res.status in ("OPTIMAL", "SUBOPTIMAL", "TIME_LIMIT")
    assert res.objective_km is not None and res.objective_km > 0
    # genau 6 Spiele (3 Paare × 2), jede gerichtete Paarung genau 1×
    assert len(res.games) == 6
    pairs = [(h, a) for (_, h, a) in res.games]
    assert len(set(pairs)) == 6
    # ≤1 Spiel je Team/Tag
    from collections import Counter
    for d in {g[0] for g in res.games}:
        teams_on_day = [t for (gd, h, a) in res.games if gd == d for t in (h, a)]
        assert max(Counter(teams_on_day).values()) == 1


def test_greenfield_respects_matchup_quota(teams):
    sub = [t for t in teams if t.id in ("NYY", "BOS", "TBR")]
    inst = round_robin_instance(sub, games_per_pair=2, n_days=9, max_consecutive=4)
    try:
        res = solve_greenfield(inst, time_limit_s=20)
    except GurobiUnavailable as exc:
        pytest.skip(f"Gurobi (Restricted) konnte nicht lösen: {exc}")
    from collections import Counter
    home = Counter(h for (_, h, a) in res.games)
    # jedes Team hostet genau 2 (1 je Gegner)
    for t in ("NYY", "BOS", "TBR"):
        assert home[t] == 2
