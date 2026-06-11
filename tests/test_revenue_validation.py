"""Tests für die Pro-Team-Revenue-Strukturvalidierung (P2-1)."""
from __future__ import annotations

import pytest

from src.datasources import LocalFileAdapter
from src.revenue import RevenueModel, build_division_rivals
from src.revenue_validation import (
    pearson, spearman, _ranks, load_real_attendance, validate_revenue_structure,
)


def test_pearson_perfect_and_inverse():
    xs = [1, 2, 3, 4, 5]
    assert pearson(xs, xs) == pytest.approx(1.0)
    assert pearson(xs, [5, 4, 3, 2, 1]) == pytest.approx(-1.0)


def test_spearman_monotonic_nonlinear():
    # Streng monoton (nichtlinear) → Spearman 1.0, Pearson < 1.0.
    xs = [1, 2, 3, 4, 5]
    ys = [1, 4, 9, 16, 25]
    assert spearman(xs, ys) == pytest.approx(1.0)
    assert pearson(xs, ys) < 1.0


def test_ranks_handles_ties():
    r = _ranks([10, 10, 20])
    assert r[0] == r[1]               # Ties = gleicher Durchschnittsrang
    assert r[2] > r[0]


def test_load_real_attendance():
    att = load_real_attendance(2024)
    assert len(att) == 30
    assert att["LAD"] > att["OAK"]    # Plausibilität


def test_structure_strong_rank_correlation(data_dir):
    season = LocalFileAdapter(base_dir=str(data_dir)).fetch_season_schedule(2024)
    from src.data_loader import load_teams
    rivals = build_division_rivals(load_teams())
    model = RevenueModel.load()
    att = load_real_attendance(2024)
    rep = validate_revenue_structure(season, model, rivals, att)
    # Akzeptanzkriterium: das Modell rankt die Teams strukturell wie die Realität.
    assert rep.spearman >= 0.80
    assert rep.pearson >= 0.70
    assert len(rep.per_team) == 30
    assert set(rep.summary()) >= {"spearman", "pearson", "ratio_spread"}
