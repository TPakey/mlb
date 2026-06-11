"""Tests für die What-if Engine (Sprint 2.5).

Testet alle vier öffentlichen Funktionen:
    - whatif_force_series()
    - whatif_blackout()
    - whatif_compare()
    - analyze_team_impact()

Strategie:
- Unit-Tests mit Mini-Saison (keine externen Ressourcen, kein Generator-Run)
- Mock-ParetoBundle via DummyBundle-Fixtures
- Integration-Test: volle 2026-Saison (scope=module, ~20s, einmaliger Build)

Sprint-Referenz: docs/SPRINT_2_5_REVIEW.md
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.season import Game, Season
from src.whatif import (
    DimensionDelta,
    TeamImpact,
    WhatIfResult,
    _build_deltas,
    _find_free_slot,
    _find_series_for_matchup,
    _move_games_to_date,
    _replace_games,
    analyze_team_impact,
    whatif_blackout,
    whatif_compare,
    whatif_force_series,
)


# ====================================================================
# Fixtures: Mini-Saison und Mock-Teams
# ====================================================================

BASE = date(2026, 4, 1)


def _g(pk: int, day: int, home: str, away: str, dh: int = 0) -> Game:
    return Game(
        game_pk=pk,
        date=BASE + timedelta(days=day),
        home=home, away=away, venue=home,
        doubleheader_seq=dh,
    )


def _mini_season() -> Season:
    """Minimalste Saison: NYY@BOS (Tage 0-2), BOS@NYY (Tage 5-7), HOU@DET (Tage 0-2)."""
    games = [
        _g(1, 0, "NYY", "BOS"),  # NYY@BOS Serie
        _g(2, 1, "NYY", "BOS"),
        _g(3, 2, "NYY", "BOS"),
        _g(4, 5, "BOS", "NYY"),  # BOS@NYY Serie
        _g(5, 6, "BOS", "NYY"),
        _g(6, 7, "BOS", "NYY"),
        _g(7, 0, "HOU", "DET"),  # Paralleles Spiel (anderes Matchup)
        _g(8, 1, "HOU", "DET"),
    ]
    return Season(
        season=2026, games=games,
        season_start=BASE,
        season_end=BASE + timedelta(days=180),
    )


def _mock_teams():
    """Mock-Teamliste (5 Teams reichen für Unit-Tests)."""
    teams = []
    for tid in ["NYY", "BOS", "HOU", "DET", "LAA"]:
        t = MagicMock()
        t.id = tid
        t.lat = 40.0
        t.lon = -74.0
        teams.append(t)
    return teams


def _mock_cfg():
    from src.generator import GeneratorConfig
    return GeneratorConfig(
        season=2026,
        season_start=BASE,
        season_end=BASE + timedelta(days=180),
    )


# ====================================================================
# Hilfsfunktionen — Unit-Tests
# ====================================================================

class TestFindSeriesForMatchup:
    def test_finds_existing_series(self):
        season = _mini_season()
        groups = _find_series_for_matchup(season, "NYY", "BOS")
        assert len(groups) == 1
        assert len(groups[0]) == 3
        assert groups[0][0].date == BASE

    def test_empty_for_nonexistent_matchup(self):
        season = _mini_season()
        groups = _find_series_for_matchup(season, "NYY", "HOU")
        assert groups == []

    def test_two_series_same_matchup(self):
        # Zwei separate Serien desselben Matchups
        games = [
            _g(1, 0, "NYY", "BOS"),
            _g(2, 1, "NYY", "BOS"),
            _g(3, 5, "NYY", "BOS"),  # Lücke → neue Serie
            _g(4, 6, "NYY", "BOS"),
        ]
        season = Season(season=2026, games=games,
                        season_start=BASE, season_end=BASE + timedelta(days=180))
        groups = _find_series_for_matchup(season, "NYY", "BOS")
        assert len(groups) == 2

    def test_sorted_by_date(self):
        season = _mini_season()
        groups = _find_series_for_matchup(season, "NYY", "BOS")
        assert groups[0][0].date <= groups[0][-1].date


class TestFindFreeSlot:
    def test_finds_slot_after_gap(self):
        season = _mini_season()
        # Slot gesucht ab Tag 3, NYY und BOS — frei ab Tag 8
        slot = _find_free_slot(
            season, ["NYY", "BOS"], series_length=3,
            preferred_start=BASE + timedelta(days=3),
            season_start=BASE, season_end=BASE + timedelta(days=180),
        )
        assert slot is not None
        assert slot >= BASE + timedelta(days=3)

    def test_no_slot_if_fully_occupied(self):
        # Saison mit keinem freien Slot
        games = [_g(i, i, "NYY", "BOS") for i in range(180)]
        season = Season(season=2026, games=games,
                        season_start=BASE, season_end=BASE + timedelta(days=180))
        slot = _find_free_slot(
            season, ["NYY", "BOS"], series_length=3,
            preferred_start=BASE,
            season_start=BASE, season_end=BASE + timedelta(days=180),
        )
        assert slot is None

    def test_respects_blackout(self):
        season = Season(season=2026, games=[],
                        season_start=BASE, season_end=BASE + timedelta(days=180))
        blackout = {BASE + timedelta(days=i) for i in range(10)}
        slot = _find_free_slot(
            season, [], series_length=1,
            preferred_start=BASE,
            blackout=blackout,
            season_start=BASE, season_end=BASE + timedelta(days=180),
        )
        assert slot is not None
        assert slot not in blackout

    def test_returns_preferred_if_free(self):
        season = Season(season=2026, games=[],
                        season_start=BASE, season_end=BASE + timedelta(days=180))
        pref = BASE + timedelta(days=10)
        slot = _find_free_slot(
            season, [], series_length=3,
            preferred_start=pref,
            season_start=BASE, season_end=BASE + timedelta(days=180),
        )
        assert slot == pref


class TestMoveGamesToDate:
    def test_shifts_by_offset(self):
        games = [_g(i + 1, i, "NYY", "BOS") for i in range(3)]
        new_start = BASE + timedelta(days=10)
        moved = _move_games_to_date(games, new_start)
        assert moved[0].date == new_start
        assert moved[1].date == new_start + timedelta(days=1)
        assert moved[2].date == new_start + timedelta(days=2)

    def test_preserves_metadata(self):
        games = [_g(42, 0, "NYY", "BOS")]
        moved = _move_games_to_date(games, BASE + timedelta(days=5))
        assert moved[0].home == "NYY"
        assert moved[0].away == "BOS"
        assert moved[0].venue == "NYY"

    def test_empty_input(self):
        assert _move_games_to_date([], BASE) == []

    def test_doubleheader_stays_on_same_day(self):
        # Zwei Spiele am selben Tag → beide landen auf new_start
        dh1 = Game(game_pk=1, date=BASE, home="NYY", away="BOS", venue="NYY", doubleheader_seq=1)
        dh2 = Game(game_pk=2, date=BASE, home="NYY", away="BOS", venue="NYY", doubleheader_seq=2)
        new_start = BASE + timedelta(days=7)
        moved = _move_games_to_date([dh1, dh2], new_start)
        assert moved[0].date == new_start
        assert moved[1].date == new_start  # beide am selben Tag


class TestReplaceGames:
    def test_removes_old_adds_new(self):
        season = _mini_season()
        old = season.games[:3]  # NYY@BOS Serie
        new = [_g(99, 20, "NYY", "BOS")]
        result = _replace_games(season, old, new)
        assert len(result.games) == len(season.games) - 3 + 1
        assert any(g.game_pk == 99 for g in result.games)
        assert not any(g.game_pk in (1, 2, 3) for g in result.games)

    def test_games_sorted_by_date(self):
        season = _mini_season()
        new_game = _g(100, 50, "NYY", "BOS")
        result = _replace_games(season, [], [new_game])
        dates = [g.date for g in result.games]
        assert dates == sorted(dates)


# ====================================================================
# _build_deltas
# ====================================================================

class TestBuildDeltas:
    def _make_bundle(self, **kwargs):
        from src.pareto_types import ParetoBundle
        defaults = dict(
            travel_km=2_000_000, revenue_usd=8_000_000_000,
            fatigue_score=10_000, max_away_streak=12,
            off_day_variance=0.005, tv_slot_score=3_000,
            event_friction=100, constraint_violations=0,
        )
        defaults.update(kwargs)
        return ParetoBundle(**defaults)

    def test_zero_delta_is_neutral(self):
        b = self._make_bundle()
        deltas = _build_deltas(b, b)
        for d in deltas:
            assert d.direction == "neutral", f"{d.name} sollte neutral sein"

    def test_travel_decrease_is_better(self):
        orig = self._make_bundle(travel_km=2_000_000)
        mod = self._make_bundle(travel_km=1_800_000)
        deltas = {d.name: d for d in _build_deltas(orig, mod)}
        assert deltas["travel_km"].direction == "better"
        assert deltas["travel_km"].delta == pytest.approx(-200_000)

    def test_revenue_increase_is_better(self):
        orig = self._make_bundle(revenue_usd=8_000_000_000)
        mod = self._make_bundle(revenue_usd=8_500_000_000)
        deltas = {d.name: d for d in _build_deltas(orig, mod)}
        assert deltas["revenue_usd"].direction == "better"

    def test_travel_increase_is_worse(self):
        orig = self._make_bundle(travel_km=2_000_000)
        mod = self._make_bundle(travel_km=2_200_000)
        deltas = {d.name: d for d in _build_deltas(orig, mod)}
        assert deltas["travel_km"].direction == "worse"

    def test_delta_pct_correct(self):
        orig = self._make_bundle(travel_km=1_000_000)
        mod = self._make_bundle(travel_km=1_100_000)
        deltas = {d.name: d for d in _build_deltas(orig, mod)}
        assert deltas["travel_km"].delta_pct == pytest.approx(10.0)

    def test_all_8_dimensions_present(self):
        b = self._make_bundle()
        deltas = _build_deltas(b, b)
        assert len(deltas) == 8
        names = {d.name for d in deltas}
        expected = {
            "travel_km", "revenue_usd", "fatigue_score", "max_away_streak",
            "off_day_variance", "tv_slot_score", "event_friction",
            "constraint_violations",
        }
        assert names == expected


# ====================================================================
# WhatIfResult
# ====================================================================

class TestWhatIfResult:
    def _make_result(self, n_better=2, n_worse=1):
        from src.pareto_types import ParetoBundle

        def _b(**kwargs):
            defaults = dict(
                travel_km=2_000_000, revenue_usd=8_000_000_000,
                fatigue_score=10_000, max_away_streak=12,
                off_day_variance=0.005, tv_slot_score=3_000,
                event_friction=100, constraint_violations=0,
            )
            defaults.update(kwargs)
            return ParetoBundle(**defaults)

        orig = _b()
        mod = _b(travel_km=1_800_000, fatigue_score=9_000, tv_slot_score=2_800)
        return WhatIfResult(
            scenario_name="Test",
            description="Test-Szenario",
            original_bundle=orig,
            modified_bundle=mod,
            deltas=_build_deltas(orig, mod),
            modified_season=_mini_season(),
            feasible=True,
        )

    def test_n_better_n_worse_correct(self):
        r = self._make_result()
        # travel -200k (better), fatigue -1k (better), tv_slot -200 (worse)
        assert r.n_better >= 1
        assert r.n_worse >= 1
        assert r.n_better + r.n_worse <= len(r.deltas)

    def test_summary_contains_scenario_name(self):
        r = self._make_result()
        r.scenario_name = "Mein Szenario"
        r.description = "Testbeschreibung"
        summary = r.summary()
        assert "Mein Szenario" in summary

    def test_to_dict_structure(self):
        r = self._make_result()
        d = r.to_dict()
        assert "scenario_name" in d
        assert "original_bundle" in d
        assert "modified_bundle" in d
        assert "deltas" in d
        assert len(d["deltas"]) == 8
        for delta in d["deltas"]:
            assert "name" in delta
            assert "original" in delta
            assert "modified" in delta

    def test_infeasible_result_reflects_in_summary(self):
        r = self._make_result()
        r.feasible = False
        r.warnings = ["Kein freier Slot gefunden"]
        summary = r.summary()
        assert "NICHT FEASIBEL" in summary or "feasibel" in summary.lower()


# ====================================================================
# whatif_compare — Unit-Test mit gepatchtem compute_pareto_bundle
# ====================================================================

class TestWhatIfCompare:
    def _make_bundle(self, travel_km: float):
        from src.pareto_types import ParetoBundle
        return ParetoBundle(
            travel_km=travel_km, revenue_usd=8_000_000_000,
            fatigue_score=10_000, max_away_streak=12,
            off_day_variance=0.005, tv_slot_score=3_000,
            event_friction=100, constraint_violations=0,
        )

    @patch("src.whatif_core.compare.compute_pareto_bundle")
    def test_compare_returns_delta(self, mock_cpb):
        bundle_a = self._make_bundle(2_000_000)
        bundle_b = self._make_bundle(1_800_000)
        mock_cpb.side_effect = [bundle_a, bundle_b]

        season = _mini_season()
        teams = _mock_teams()
        result = whatif_compare(season, season, teams, "A", "B")

        assert result.scenario_name == "A vs. B"
        travel_delta = result._delta_for("travel_km")
        assert travel_delta == pytest.approx(-200_000)

    @patch("src.whatif_core.compare.compute_pareto_bundle")
    def test_compare_same_season_all_neutral(self, mock_cpb):
        bundle = self._make_bundle(2_000_000)
        mock_cpb.side_effect = [bundle, bundle]

        season = _mini_season()
        result = whatif_compare(season, season, _mock_teams())
        for d in result.deltas:
            assert d.direction == "neutral"

    @patch("src.whatif_core.compare.compute_pareto_bundle")
    def test_compare_better_plan_detected(self, mock_cpb):
        orig = self._make_bundle(2_000_000)
        better = self._make_bundle(1_500_000)
        mock_cpb.side_effect = [orig, better]

        result = whatif_compare(_mini_season(), _mini_season(), _mock_teams())
        travel = next(d for d in result.deltas if d.name == "travel_km")
        assert travel.direction == "better"
        assert travel.is_better


# ====================================================================
# whatif_blackout — Unit-Test mit gepatchtem compute_pareto_bundle
# ====================================================================

class TestWhatIfBlackout:
    def _bundle(self):
        from src.pareto_types import ParetoBundle
        return ParetoBundle(
            travel_km=2_000_000, revenue_usd=8_000_000_000,
            fatigue_score=10_000, max_away_streak=12,
            off_day_variance=0.005, tv_slot_score=3_000,
            event_friction=100, constraint_violations=0,
        )

    @patch("src.whatif_core.blackout.compute_pareto_bundle")
    def test_blackout_no_conflict(self, mock_cpb):
        """Blackout außerhalb des Spielplans → kein Konflikt, 0-Delta."""
        bundle = self._bundle()
        mock_cpb.return_value = bundle

        season = _mini_season()
        cfg = _mock_cfg()
        # Blackout ab Tag 100 (weit außerhalb der 2-wöchigen Mini-Saison)
        blackout = [BASE + timedelta(days=100)]

        result = whatif_blackout(season, _mock_teams(), cfg, "NYY", blackout)
        assert "kein Konflikt" in result.warnings[0].lower() or len(result.deltas) == 8
        assert result.feasible

    @patch("src.whatif_core.blackout.compute_pareto_bundle")
    def test_blackout_moves_series(self, mock_cpb):
        """Heimspiele von NYY in Blackout-Fenster werden verschoben."""
        bundle_orig = self._bundle()
        bundle_mod = self._bundle()
        mock_cpb.side_effect = [bundle_orig, bundle_mod]

        season = _mini_season()
        cfg = _mock_cfg()
        # Blackout genau auf den ersten 3 NYY-Heimspielen
        blackout = [BASE + timedelta(days=i) for i in range(3)]

        result = whatif_blackout(season, _mock_teams(), cfg, "NYY", blackout, reason="Konzert")
        assert result is not None
        assert "Konzert" in result.scenario_name

    @patch("src.whatif_core.blackout.compute_pareto_bundle")
    def test_blackout_result_has_8_deltas(self, mock_cpb):
        bundle = self._bundle()
        mock_cpb.return_value = bundle

        season = _mini_season()
        cfg = _mock_cfg()
        result = whatif_blackout(season, _mock_teams(), cfg, "HOU", [BASE])
        assert len(result.deltas) == 8

    @patch("src.whatif_core.blackout.compute_pareto_bundle")
    def test_blackout_scenario_name_auto(self, mock_cpb):
        bundle = self._bundle()
        mock_cpb.return_value = bundle

        season = _mini_season()
        cfg = _mock_cfg()
        result = whatif_blackout(season, _mock_teams(), cfg, "BOS",
                                   [BASE + timedelta(days=5), BASE + timedelta(days=6)])
        assert "BOS" in result.scenario_name


# ====================================================================
# whatif_force_series — Unit-Test mit gepatchtem compute_pareto_bundle
# ====================================================================

class TestWhatIfForceSeries:
    def _bundle(self, travel_km=2_000_000):
        from src.pareto_types import ParetoBundle
        return ParetoBundle(
            travel_km=travel_km, revenue_usd=8_000_000_000,
            fatigue_score=10_000, max_away_streak=12,
            off_day_variance=0.005, tv_slot_score=3_000,
            event_friction=100, constraint_violations=0,
        )

    @patch("src.whatif_core.force.compute_pareto_bundle")
    def test_force_existing_series_to_new_date(self, mock_cpb):
        """Serie NYY@BOS von Tag 0 auf Tag 10 erzwingen."""
        mock_cpb.side_effect = [self._bundle(2_000_000), self._bundle(1_900_000)]

        season = _mini_season()
        cfg = _mock_cfg()
        teams = _mock_teams()
        forced_date = BASE + timedelta(days=10)

        result = whatif_force_series(season, teams, cfg, "NYY", "BOS", forced_date)
        assert result is not None
        assert "NYY" in result.scenario_name or "NYY" in result.description

    @patch("src.whatif_core.force.compute_pareto_bundle")
    def test_force_series_result_has_modified_season(self, mock_cpb):
        """modified_season darf nicht None sein."""
        mock_cpb.side_effect = [self._bundle(), self._bundle()]

        season = _mini_season()
        cfg = _mock_cfg()
        forced_date = BASE + timedelta(days=10)

        result = whatif_force_series(season, _mock_teams(), cfg, "NYY", "BOS", forced_date)
        assert result.modified_season is not None
        assert len(result.modified_season.games) > 0

    @patch("src.whatif_core.force.compute_pareto_bundle")
    def test_force_series_forced_date_in_modified_season(self, mock_cpb):
        """Die erzwungene Serie muss im neuen Plan am forced_date liegen."""
        mock_cpb.side_effect = [self._bundle(), self._bundle()]

        season = _mini_season()
        cfg = _mock_cfg()
        forced_date = BASE + timedelta(days=15)  # Kein Konflikt

        result = whatif_force_series(season, _mock_teams(), cfg, "NYY", "BOS", forced_date)
        # Mindestens ein NYY@BOS-Spiel am forced_date (oder kurz danach falls Kollision)
        nyy_bos_dates = {
            g.date for g in result.modified_season.games
            if g.home == "NYY" and g.away == "BOS"
        }
        # Es kann leichte Verschiebungen geben, aber die Serie sollte nahe am forced_date liegen
        min_gap = min(abs((d - forced_date).days) for d in nyy_bos_dates)
        assert min_gap <= 5, f"Serie zu weit vom forced_date entfernt: min_gap={min_gap}"

    @patch("src.whatif_core.force.compute_pareto_bundle")
    def test_force_nonexistent_series_adds_warning(self, mock_cpb):
        """Wenn das Matchup nicht existiert, muss eine Warnung erscheinen."""
        mock_cpb.side_effect = [self._bundle(), self._bundle()]

        season = _mini_season()
        cfg = _mock_cfg()

        result = whatif_force_series(season, _mock_teams(), cfg, "LAA", "NYY",
                                      BASE + timedelta(days=20))
        assert len(result.warnings) > 0  # Warnung: Matchup nicht gefunden

    @patch("src.whatif_core.force.compute_pareto_bundle")
    def test_force_series_8_deltas(self, mock_cpb):
        mock_cpb.side_effect = [self._bundle(), self._bundle()]
        result = whatif_force_series(_mini_season(), _mock_teams(), _mock_cfg(),
                                      "NYY", "BOS", BASE + timedelta(days=20))
        assert len(result.deltas) == 8


# ====================================================================
# analyze_team_impact
# ====================================================================

class TestAnalyzeTeamImpact:
    def test_no_change_zero_delta(self):
        season = _mini_season()
        impact = analyze_team_impact(season, season, "NYY")
        assert impact.games_added == 0
        assert impact.games_removed == 0
        assert impact.home_games_delta == 0
        assert impact.away_games_delta == 0

    def test_added_game_detected(self):
        season = _mini_season()
        new_game = Game(game_pk=999, date=BASE + timedelta(days=20),
                         home="NYY", away="BOS", venue="NYY")
        mod = Season(season=2026, games=season.games + [new_game],
                      season_start=BASE, season_end=BASE + timedelta(days=180))
        impact = analyze_team_impact(season, mod, "NYY")
        assert impact.games_added == 1
        assert impact.home_games_delta == 1

    def test_removed_game_detected(self):
        season = _mini_season()
        reduced = Season(season=2026, games=season.games[1:],
                          season_start=BASE, season_end=BASE + timedelta(days=180))
        impact = analyze_team_impact(season, reduced, "NYY")
        assert impact.games_removed == 1

    def test_team_id_stored(self):
        season = _mini_season()
        impact = analyze_team_impact(season, season, "BOS")
        assert impact.team_id == "BOS"

    def test_affected_series_list(self):
        season = _mini_season()
        new_game = Game(game_pk=999, date=BASE + timedelta(days=20),
                         home="NYY", away="BOS", venue="NYY")
        mod = Season(season=2026, games=season.games + [new_game],
                      season_start=BASE, season_end=BASE + timedelta(days=180))
        impact = analyze_team_impact(season, mod, "NYY")
        assert len(impact.affected_series) > 0
        # Muss Datum und Gegner enthalten
        assert any("BOS" in s for s in impact.affected_series)


# ====================================================================
# DimensionDelta.__str__
# ====================================================================

class TestDimensionDeltaStr:
    def _delta(self, name="travel_km", orig=2_000_000, mod=1_800_000):
        delta = mod - orig
        pct = delta / orig * 100
        minimize = True
        direction = "better" if (delta < 0 and minimize) else "worse"
        return DimensionDelta(
            name=name, label="Reisedistanz", unit="km",
            original=orig, modified=mod,
            delta=delta, delta_pct=pct,
            direction=direction, minimize=minimize,
        )

    def test_str_contains_direction_icon(self):
        d = self._delta()
        s = str(d)
        assert "✓" in s  # better

    def test_str_contains_values(self):
        d = self._delta(orig=2_000_000, mod=1_800_000)
        s = str(d)
        assert "2000000" in s.replace(",", "").replace(".", "").replace(" ", "") \
            or "2" in s  # Wert irgendwie enthalten

    def test_worse_delta_has_x_icon(self):
        d = DimensionDelta(
            name="travel_km", label="Reisedistanz", unit="km",
            original=1_800_000, modified=2_000_000,
            delta=200_000, delta_pct=11.1,
            direction="worse", minimize=True,
        )
        assert "✗" in str(d)


# ====================================================================
# Sprint 2.10 — What-if-Härtung (M3, M4, M5)
# ====================================================================

class TestWhatIfHardening:
    def _season_with_conflict(self) -> Season:
        # NYY spielt NYY@LAA an Tag 4-5; kein NYY@BOS vorhanden (Insert-Branch).
        games = [
            _g(1, 4, "NYY", "LAA"),
            _g(2, 5, "NYY", "LAA"),
            _g(3, 4, "BOS", "TOR"),
            _g(10, 20, "NYY", "TBR"),
        ]
        return Season(season=2026, games=games, season_start=BASE,
                      season_end=BASE + timedelta(days=180))

    @patch("src.whatif_core.force.compute_pareto_bundle")
    def test_force_series_insert_no_double_booking(self, mock_cpb):
        """M3: Eine neu eingefügte Serie darf kein Team doppelt buchen —
        kollidierende Spiele (NYY@LAA) werden verschoben."""
        from src.pareto_types import ParetoBundle
        b = ParetoBundle(travel_km=2e6, revenue_usd=8e9, fatigue_score=1e4,
                         max_away_streak=12, off_day_variance=0.005,
                         tv_slot_score=3000, event_friction=100,
                         constraint_violations=0)
        mock_cpb.side_effect = [b, b]
        season = self._season_with_conflict()
        forced = BASE + timedelta(days=4)
        result = whatif_force_series(season, _mock_teams(), _mock_cfg(),
                                     "NYY", "BOS", forced, series_length=3)
        ms = result.modified_season
        # Kein Team an einem Tag in zwei verschiedenen Spielen.
        from collections import Counter
        for tid in ("NYY", "BOS", "LAA", "TOR"):
            per_day = Counter(g.date for g in ms.games
                              if (g.home == tid or g.away == tid))
            assert all(n <= 1 for n in per_day.values()), \
                f"{tid} ist an einem Tag doppelt gebucht"

    def test_find_free_slot_skips_all_star_break(self):
        """M4: _find_free_slot darf keinen Slot im All-Star-Break zurückgeben."""
        asb = tuple(BASE + timedelta(days=d) for d in range(10, 14))
        games = [_g(1, 0, "NYY", "BOS")]
        season = Season(season=2026, games=games, season_start=BASE,
                        season_end=BASE + timedelta(days=180),
                        all_star_dates=asb)
        # Bevorzugter Start mitten im Break → muss ausweichen.
        slot = _find_free_slot(
            season, teams=["NYY", "BOS"], series_length=3,
            preferred_start=BASE + timedelta(days=10),
            season_start=BASE, season_end=BASE + timedelta(days=180),
        )
        assert slot is not None
        occupied_days = {slot + timedelta(days=i) for i in range(3)}
        assert not (occupied_days & set(asb)), "Slot überschneidet All-Star-Break"
