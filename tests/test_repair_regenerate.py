"""Tests fuer Strategie B — Constrained Re-Generate (src/repair_regenerate.py).

Strategie B nutzt den vollen CP-SAT-Pipeline-Lauf. Tests sind deshalb
teuer (10+ s pro Aufruf). Wir halten sie minimal und marken sie mit
@pytest.mark.slow, damit sie in CI-Light-Runs gespart werden koennen.
"""
from __future__ import annotations

from datetime import date

import pytest

from src.disruption_types import StadiumBlackout
from src.generator import GeneratorConfig
from src.repair_regenerate import repair_regenerate


@pytest.fixture(scope="module")
def quotas_and_baseline():
    from src.datasources import LocalFileAdapter
    from src.generator import generate
    from src.matchup_extractor import extract_matchup_quotas

    adapter = LocalFileAdapter(base_dir="data")
    season_2024 = adapter.fetch_season_schedule(2024)
    quotas = extract_matchup_quotas(season_2024)
    cfg = GeneratorConfig(
        season=2026,
        season_start=date(2026, 3, 26),
        season_end=date(2026, 9, 27),
        all_star_break=(date(2026, 7, 13), date(2026, 7, 16)),
        max_solver_time_seconds=60,
        num_search_workers=1,
        travel_optimizer_iterations=50_000,   # schnell fuer Tests
    )
    baseline = generate(quotas, cfg)
    return cfg, baseline.season


@pytest.fixture(scope="module")
def teams_city_lookup():
    from src.data_loader import load_teams
    return {t.id: t.city for t in load_teams()}


@pytest.mark.slow
def test_short_blackout_returns_valid_plan(quotas_and_baseline, teams_city_lookup):
    """Kurzer NYY-Blackout: Re-Generate liefert validen Plan ohne NYY-Heimspiele
    im Fenster."""
    cfg, baseline = quotas_and_baseline
    disruption = StadiumBlackout(
        home_team="NYY",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 7),
        reason="Smoke-Test",
    )
    new_season, changes, result = repair_regenerate(
        baseline, disruption, cfg, teams_city_lookup
    )
    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert new_season is not None
    # Keine NYY-Heimspiele im Disruption-Fenster
    nyy_home_in_window = [
        g for g in new_season.games
        if g.home == "NYY" and date(2026, 5, 1) <= g.date <= date(2026, 5, 7)
    ]
    assert nyy_home_in_window == [], \
        f"NYY-Heimspiel im Disruption-Fenster: {nyy_home_in_window}"


@pytest.mark.slow
def test_total_games_preserved(quotas_and_baseline, teams_city_lookup):
    """Re-Generate erhaelt die Gesamtzahl der Spiele."""
    cfg, baseline = quotas_and_baseline
    disruption = StadiumBlackout(
        home_team="BAL",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 5),
    )
    new_season, changes, result = repair_regenerate(
        baseline, disruption, cfg, teams_city_lookup
    )
    assert len(new_season.games) == len(baseline.games)
