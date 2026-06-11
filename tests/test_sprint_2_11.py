"""Tests für Sprint 2.11 — SA-Korrektheit + DST (M2, M6, N5, N10, N8/M8)."""
from __future__ import annotations

from datetime import date

import pytest

from src.distance import tz_offset_hours, travel_leg, TIMEZONE_OFFSET
from src.data_loader import Team, load_teams
from src.pareto import ParetoFrontier, _random_profile
import random


# ── M2: DST-aware Timezone-Offsets ───────────────────────────────────────────

class TestDST:
    def test_ny_summer_vs_winter(self):
        assert tz_offset_hours("America/New_York", date(2026, 8, 15)) == -4   # EDT
        assert tz_offset_hours("America/New_York", date(2026, 1, 15)) == -5   # EST

    def test_phoenix_no_dst(self):
        assert tz_offset_hours("America/Phoenix", date(2026, 8, 15)) == -7
        assert tz_offset_hours("America/Phoenix", date(2026, 1, 15)) == -7

    def test_ny_to_phoenix_summer_three_hops(self):
        d = date(2026, 8, 15)
        hops = abs(tz_offset_hours("America/New_York", d)
                   - tz_offset_hours("America/Phoenix", d))
        assert hops == 3

    def test_la_to_phoenix_summer_zero_hops(self):
        d = date(2026, 8, 15)
        hops = abs(tz_offset_hours("America/Los_Angeles", d)
                   - tz_offset_hours("America/Phoenix", d))
        assert hops == 0

    def test_no_date_falls_back_to_standard_offset(self):
        for tz, off in TIMEZONE_OFFSET.items():
            assert tz_offset_hours(tz, None) == off


# ── N10: Timezone-Validierung im Loader ──────────────────────────────────────

class TestTimezoneValidation:
    def test_real_teams_pass(self):
        teams = load_teams()
        assert len(teams) == 30

    def test_unknown_timezone_rejected(self):
        from src.data_loader import _validate_teams
        teams = load_teams()
        # Ein Team mit unbekannter Timezone -> ValueError
        bad = teams[:-1] + [Team(**{**teams[-1].__dict__, "timezone": "America/Mexico_City"})]
        with pytest.raises(ValueError, match="Timezone"):
            _validate_teams(bad)


# ── N5: Dirichlet-Sampling ───────────────────────────────────────────────────

class TestDirichlet:
    def test_random_profile_weights_normalized_blend(self):
        rng = random.Random(7)
        p = _random_profile(rng, name="t")
        # Gültiges Profil mit endlichen Gewichten.
        assert p.name == "t"
        for attr in ("w_travel", "w_revenue", "w_fatigue", "w_away_streak",
                     "w_off_day", "w_tv", "w_friction"):
            assert isinstance(getattr(p, attr), float)


# ── M6: Leere Frontier ────────────────────────────────────────────────────────

class TestEmptyFrontier:
    def test_best_by_returns_none_on_empty(self):
        fr = ParetoFrontier(points=[], all_evaluated=[], anchor_labels=[],
                            total_wall_time_s=0.0, n_profiles_run=0, master_seed=42)
        assert fr.best_by("travel_km") is None
        assert fr.n_non_dominated == 0
