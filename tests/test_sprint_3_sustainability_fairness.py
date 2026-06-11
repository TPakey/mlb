"""Tests für Sprint 3 / Track C — CO₂- (C1) und Fairness-Modelle (C2).

Schnell (< 1 s): reine Mathematik + Integration mit dem realen Travel-Report.
"""
from __future__ import annotations

import pytest

from src import fairness, sustainability
from src.data_loader import load_teams
from src.datasources import LocalFileAdapter
from src.travel import compute_season_travel


# ---------------------------------------------------------------
# C1 — CO₂
# ---------------------------------------------------------------

def test_co2_factor_is_product_of_cited_factors():
    assert sustainability.CO2_KG_PER_KM == pytest.approx(3.16 * 3.98)
    assert sustainability.CO2_KG_PER_KM == pytest.approx(12.5768, abs=1e-3)


def test_co2_conversion_scales_linearly():
    assert sustainability.co2_kg_from_km(0) == 0.0
    assert sustainability.co2_tonnes_from_km(1000) == pytest.approx(
        sustainability.CO2_KG_PER_KM, rel=1e-9)
    # 2 Mio km -> plausible Liga-Größenordnung (~25k t)
    t = sustainability.co2_tonnes_from_km(2_000_000)
    assert 20_000 < t < 30_000


def test_co2_report_on_real_plan():
    adapter = LocalFileAdapter(base_dir="data")
    season = adapter.fetch_season_schedule(2024)
    teams = load_teams()
    travel = compute_season_travel(season, teams)
    report = sustainability.compute_co2_report(travel)
    assert len(report.per_team_tonnes) == 30
    # Summe der Pro-Team-Tonnen ≈ Gesamttonnen
    assert sum(report.per_team_tonnes.values()) == pytest.approx(
        report.total_tonnes, rel=1e-6)
    assert report.total_tonnes > 0


# ---------------------------------------------------------------
# C2 — Fairness
# ---------------------------------------------------------------

def test_gini_perfectly_equal_is_zero():
    assert fairness.gini([100, 100, 100, 100]) == pytest.approx(0.0)


def test_gini_increases_with_inequality():
    equalish = fairness.gini([90, 100, 110])
    skewed = fairness.gini([10, 10, 280])
    assert skewed > equalish > 0


def test_gini_edge_cases():
    assert fairness.gini([]) == 0.0
    assert fairness.gini([42]) == 0.0
    assert fairness.gini([0, 0, 0]) == 0.0


def test_gini_bounds():
    # Maximal ungleich (einer hat alles) → nahe (n-1)/n
    g = fairness.gini([0, 0, 0, 1000])
    assert 0.0 < g < 1.0


def test_disparity_ratio():
    assert fairness.disparity_ratio([50, 100, 200]) == pytest.approx(4.0)
    assert fairness.disparity_ratio([]) == 0.0
    assert fairness.disparity_ratio([0, 100]) == 0.0  # min <= 0


def test_fairness_report_on_real_plan():
    adapter = LocalFileAdapter(base_dir="data")
    season = adapter.fetch_season_schedule(2024)
    teams = load_teams()
    travel = compute_season_travel(season, teams)
    rep = fairness.compute_fairness_report(travel)
    assert len(rep.per_team_km) == 30
    assert 0.0 < rep.gini < 0.5          # reale Liga ist moderat ungleich
    assert rep.disparity_ratio > 1.0
    assert rep.max_km >= rep.mean_km >= rep.min_km
    assert rep.max_team and rep.min_team
