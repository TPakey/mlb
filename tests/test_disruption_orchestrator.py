"""Tests fuer den Disruption-Orchestrator (src/disruption.py)."""
from __future__ import annotations

from datetime import date

import pytest

from src.disruption import handle_disruption
from src.disruption_types import (
    Alternative, ScoreBundle, StadiumBlackout, StrategyKind, TradeoffReport,
)
from src.generator import GeneratorConfig


@pytest.fixture(scope="module")
def baseline():
    """Voller Sprint-2.1-Plan als Disruption-Ausgangspunkt."""
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
        travel_optimizer_iterations=50_000,   # Tests schneller halten
    )
    return cfg, generate(quotas, cfg).season


@pytest.fixture(scope="module")
def short_disruption():
    """Eine kurze, gut handhabbare Disruption (NYY 3 Tage)."""
    return StadiumBlackout(
        home_team="NYY",
        start_date=date(2026, 5, 8),
        end_date=date(2026, 5, 10),
        reason="Smoke-Test-Disruption",
    )


# ====================================================================
# AC-2.2.2: liefert genau drei Alternativen A, B, C (deterministisch)
# ====================================================================

class TestOrchestratorBasics:
    def test_AC_2_2_2_three_alternatives(self, baseline, short_disruption):
        cfg, base_season = baseline
        report = handle_disruption(base_season, short_disruption, cfg)
        assert isinstance(report, TradeoffReport)
        assert len(report.alternatives) == 3

    def test_alternatives_in_deterministic_order(self, baseline, short_disruption):
        cfg, base_season = baseline
        report = handle_disruption(base_season, short_disruption, cfg)
        kinds = [a.strategy for a in report.alternatives]
        assert kinds == [
            StrategyKind.LOCAL_REPAIR,
            StrategyKind.CONSTRAINED_REGENERATE,
            StrategyKind.VENUE_SWAP,
        ]

    def test_AC_2_2_4_score_bundle_complete(self, baseline, short_disruption):
        cfg, base_season = baseline
        report = handle_disruption(base_season, short_disruption, cfg)
        for alt in report.alternatives:
            assert isinstance(alt.score, ScoreBundle)
            assert alt.score.travel_km_delta is not None
            assert alt.score.affected_teams is not None
            assert alt.score.revenue_delta_usd is not None
            assert alt.score.fatigue_delta is not None
            assert 0 <= alt.score.change_pct <= 1
            assert alt.score.hard_constraint_violations >= 0


# ====================================================================
# AC-2.2.1: Performance — <= 60s Response-Zeit
# ====================================================================

class TestPerformance:
    @pytest.mark.slow
    def test_AC_2_2_1_under_60_seconds(self, baseline, short_disruption):
        cfg, base_season = baseline
        report = handle_disruption(base_season, short_disruption, cfg)
        assert report.total_runtime_seconds <= 60, \
            f"Orchestrator-Run: {report.total_runtime_seconds:.1f}s (Limit 60)"


# ====================================================================
# AC-2.2.5: Strategie A = Mindestabweichung
# ====================================================================

class TestMinDeviation:
    def test_AC_2_2_5_strategy_a_low_change_pct(self, baseline, short_disruption):
        cfg, base_season = baseline
        report = handle_disruption(base_season, short_disruption, cfg)
        alt_a = report.alternatives[0]
        assert alt_a.strategy == StrategyKind.LOCAL_REPAIR
        # Bei einer 3-Tage-Disruption sollte Strategie A weniger als 5% des Plans aendern
        assert alt_a.score.change_pct <= 0.05, \
            f"Local Repair change_pct={alt_a.score.change_pct:.3f} > 5%"


# ====================================================================
# AC-2.2.7: Idempotenz
# ====================================================================

class TestReproducibility:
    @pytest.mark.slow
    def test_AC_2_2_7_idempotent_runs(self, baseline, short_disruption):
        cfg, base_season = baseline
        r1 = handle_disruption(base_season, short_disruption, cfg)
        r2 = handle_disruption(base_season, short_disruption, cfg)
        for a1, a2 in zip(r1.alternatives, r2.alternatives):
            g1 = sorted((g.date, g.game_pk, g.home, g.away) for g in a1.season.games)
            g2 = sorted((g.date, g.game_pk, g.home, g.away) for g in a2.season.games)
            assert g1 == g2, f"Strategie {a1.strategy} nicht reproduzierbar"


# ====================================================================
# AC-2.2.8: Alternativen-Diversitaet
# ====================================================================

class TestDiversity:
    def test_AC_2_2_8_pairwise_differences(self, baseline, short_disruption):
        cfg, base_season = baseline
        report = handle_disruption(base_season, short_disruption, cfg)
        # Wenn alle drei identisch waeren, waere die Strategie wertlos.
        # Hier nur sanity: A und B unterscheiden sich in Spiel-Daten.
        a = report.alternatives[0].season
        b = report.alternatives[1].season
        a_dates = {(g.game_pk, g.date) for g in a.games}
        b_dates = {(g.game_pk, g.date) for g in b.games}
        diff = a_dates.symmetric_difference(b_dates)
        assert len(diff) > 0, "Strategien A und B liefern identische Plaene"
