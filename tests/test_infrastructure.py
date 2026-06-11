"""Sanity-Tests fuer die Test-Infrastruktur und Sprint-1-Foundation.

Diese Tests muessen *immer* gruen sein - sie sind die Regression-Baseline
fuer alle nachfolgenden Sprints.
"""
from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------- Infrastruktur ----------------------

def test_ortools_cp_sat_available():
    """OR-Tools CP-SAT muss importierbar sein - Voraussetzung fuer Sprint 2.1."""
    from ortools.sat.python import cp_model
    model = cp_model.CpModel()
    x = model.NewIntVar(0, 10, "x")
    model.Add(x >= 3)
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    assert solver.Value(x) >= 3


def test_hypothesis_available():
    """Hypothesis fuer Property-Based-Tests."""
    from hypothesis import given, strategies as st

    @given(st.integers(min_value=1, max_value=100))
    def _inner(n):
        assert n > 0
    _inner()


# ---------------------- Sprint-1-Foundation ----------------------

def test_teams_loaded(teams):
    assert len(teams) == 30
    leagues = {t.league for t in teams}
    assert leagues == {"AL", "NL"}


def test_division_structure(teams):
    """6 Divisionen, je 5 Teams."""
    div_counts = {}
    for t in teams:
        key = (t.league, t.division)
        div_counts[key] = div_counts.get(key, 0) + 1
    assert len(div_counts) == 6
    assert all(c == 5 for c in div_counts.values())


def test_teams_have_valid_coordinates(teams):
    for t in teams:
        # USA + Kanada Bounding Box
        assert 24 < t.lat < 50, f"{t.id}: Latitude {t.lat} ausserhalb USA/Kanada"
        assert -130 < t.lon < -65, f"{t.id}: Longitude {t.lon} ausserhalb USA/Kanada"


@pytest.mark.integration
def test_real_data_pipeline_2024(data_dir, teams):
    """Regression: 2024-Pipeline muss stabile Kennzahlen liefern."""
    schedule_file = data_dir / "mlb_schedule_2024.json"
    if not schedule_file.exists():
        pytest.skip("MLB 2024 Schedule nicht vorhanden")
    from src.datasources import LocalFileAdapter
    from src.travel import compute_season_travel
    adapter = LocalFileAdapter(base_dir=data_dir)
    season = adapter.fetch_season_schedule(2024)
    assert len(season.games) == 2432, "Genau 2432 gespielte Spiele 2024 (inkl. Seoul Series)"
    report = compute_season_travel(season, teams)
    # Sanity: Schnitt sollte ~57k km sein (Toleranz +-2%)
    assert 50_000 <= report.avg_km_per_team <= 62_000


@pytest.mark.integration
def test_real_data_pipeline_2025(data_dir, teams):
    schedule_file = data_dir / "mlb_schedule_2025.json"
    if not schedule_file.exists():
        pytest.skip("MLB 2025 Schedule nicht vorhanden")
    from src.datasources import LocalFileAdapter
    from src.travel import compute_season_travel
    adapter = LocalFileAdapter(base_dir=data_dir)
    season = adapter.fetch_season_schedule(2025)
    assert len(season.games) == 2432
    report = compute_season_travel(season, teams)
    assert 50_000 <= report.avg_km_per_team <= 62_000


def test_validation_harness_2024_regression(data_dir, teams):
    """Regression: das Sprint-1-Ergebnis darf sich nicht aendern."""
    schedule_file = data_dir / "mlb_schedule_2024.json"
    if not schedule_file.exists():
        pytest.skip("MLB 2024 nicht vorhanden")
    from src.datasources import LocalFileAdapter
    from src.legacy.validation import validate_season
    adapter = LocalFileAdapter(base_dir=data_dir)
    season = adapter.fetch_season_schedule(2024)
    result = validate_season(season, teams)
    # Sprint-1-Befund: 1.06 % Einsparung
    assert 0.95 <= result.savings_pct <= 1.15, \
        f"Sprint-1-Ergebnis hat sich geaendert: {result.savings_pct}% (Erwartung ~1.06%)"
