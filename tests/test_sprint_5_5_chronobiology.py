"""Sprint 5.5 (D1–D3) — Chronobiologie: Fairness, Sensitivität, Richtungs-Sanity,
Determinismus. Belegt, dass die Jet-Lag-Gewichte konservativ, transparent und
fair/symmetrisch sind.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from conftest import make_game, make_mini_season

from src.data_loader import load_teams
from src.datasources.local_file import LocalFileAdapter
from src.chronobiology import (
    season_jet_lag, team_jet_lag_index, _gini, DISCOUNT,
)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


@pytest.fixture(scope="module")
def teams():
    return load_teams()


@pytest.fixture(scope="module")
def tbi(teams):
    return {t.id: t for t in teams}


def _real(year):
    return LocalFileAdapter(base_dir=DATA).fetch_season_schedule(year)


# ---------- Sanity: kein TZ-Wechsel → 0 ----------

def test_no_timezone_travel_zero(tbi):
    # NYY spielt nur zuhause + bei BOS (beide ET) → keine TZ-Überquerung → 0
    games = [make_game(i, i * 3, "NYY", "BOS") for i in range(4)]
    s = make_mini_season(games)
    assert team_jet_lag_index(s, "NYY", tbi) == 0.0


# ---------- Richtungs-Sanity (D1): Ostwärts > Westwärts ----------

def test_eastward_worse_than_westward(tbi):
    base = date(2024, 4, 1)
    # Variante A: LAD reist nach NYM (ostwärts, 3 TZ) und zurück
    east = make_mini_season([
        make_game(1, 0, "LAD", "SDP"),
        make_game(2, 1, "NYM", "LAD"),   # LAD reist ostwärts
    ], season_start=base)
    # Variante B: NYM reist nach LAD (westwärts, 3 TZ) und zurück
    west = make_mini_season([
        make_game(1, 0, "NYM", "PHI"),
        make_game(2, 1, "LAD", "NYM"),   # NYM reist westwärts
    ], season_start=base)
    e = team_jet_lag_index(east, "LAD", tbi)
    w = team_jet_lag_index(west, "NYM", tbi)
    assert e > w > 0, f"ostwärts ({e}) sollte > westwärts ({w}) sein"


# ---------- Sensitivität (D2): Mapping offengelegt + monoton ----------

def test_discount_scales_linearly(teams):
    s = _real(2024)
    r1 = season_jet_lag(s, teams, discount=0.25)
    r2 = season_jet_lag(s, teams, discount=0.50)
    assert r2.total == pytest.approx(2 * r1.total, rel=1e-9)


def test_higher_east_weight_increases_burden(teams):
    s = _real(2024)
    low = season_jet_lag(s, teams, east_w=1.0).total
    high = season_jet_lag(s, teams, east_w=2.0).total
    assert high > low


# ---------- Fairness/Symmetrie (D3) ----------

def test_identical_weights_for_all_teams(teams):
    s = _real(2024)
    r = season_jet_lag(s, teams)
    # ein einziges Gewichts-Set, für alle Teams gleich
    assert r.weights["discount"] == DISCOUNT
    # der Index ist nicht-negativ für alle
    assert all(v >= 0 for v in r.per_team.values())


def test_gini_reasonable(teams):
    # Gini misst geografische Asymmetrie, nicht Modell-Unfairness; moderat.
    s = _real(2024)
    r = season_jet_lag(s, teams)
    assert 0.0 <= r.gini < 0.5


def test_west_coast_burden_exceeds_central(teams):
    # OAK/LAD (West, reisen viel ostwärts) > CHC (Central) — Plan-bedingt, fair.
    s = _real(2024)
    r = season_jet_lag(s, teams)
    assert r.per_team["OAK"] > r.per_team["CHC"]
    assert r.per_team["LAD"] > r.per_team["CHC"]


# ---------- Determinismus ----------

def test_deterministic(teams):
    s = _real(2024)
    assert season_jet_lag(s, teams).per_team == season_jet_lag(s, teams).per_team


def test_gini_helper():
    assert _gini([5, 5, 5]) == pytest.approx(0.0)
    assert _gini([0, 0, 10]) > 0.5
