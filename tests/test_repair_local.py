"""Tests fuer Strategie A — Local Repair (src/repair_local.py)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import List

import pytest

from src.disruption_types import (
    StadiumBlackout, WeatherWindow, MassPostponement,
)
from src.repair_local import repair_local, affected_games
from src.season import Game, Season


# ====================================================================
# Helpers
# ====================================================================

def _g(pk: int, day_offset: int, home: str, away: str) -> Game:
    return Game(
        game_pk=pk,
        date=date(2026, 4, 1) + timedelta(days=day_offset),
        home=home,
        away=away,
        venue=home,
    )


def _mk_season(games: List[Game], end_offset: int = 60) -> Season:
    return Season(
        season=2026,
        games=games,
        season_start=date(2026, 4, 1),
        season_end=date(2026, 4, 1) + timedelta(days=end_offset),
    )


# ====================================================================
# affected_games
# ====================================================================

class TestAffectedGames:
    def test_stadium_blackout_picks_home_games_in_window(self):
        s = _mk_season([
            _g(1, 0, "NYY", "BOS"),     # Tag 0 — NYY home
            _g(2, 1, "NYY", "BOS"),     # Tag 1 — NYY home
            _g(3, 2, "BOS", "NYY"),     # Tag 2 — BOS home, NYY away
            _g(4, 5, "NYY", "TOR"),     # Tag 5 — NYY home, OUTSIDE Blackout
        ])
        d = StadiumBlackout(
            home_team="NYY",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 3),
        )
        a = affected_games(s, d)
        assert {g.game_pk for g in a} == {1, 2}  # Tag 5 ist ausserhalb, Tag 2 ist BOS-Home

    def test_mass_postponement_picks_exact_pks(self):
        s = _mk_season([_g(1, 0, "NYY", "BOS"), _g(2, 1, "NYY", "BOS"), _g(3, 2, "NYY", "BOS")])
        d = MassPostponement(game_pks=(2, 3))
        a = affected_games(s, d)
        assert {g.game_pk for g in a} == {2, 3}

    def test_weather_window_picks_by_city(self):
        s = _mk_season([
            _g(1, 0, "TBR", "NYY"),
            _g(2, 1, "TBR", "NYY"),
            _g(3, 2, "NYY", "TBR"),    # diese ist in Bronx, nicht Tampa
        ])
        d = WeatherWindow(
            city="Tampa",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 2),
        )
        teams_city = {"TBR": "Tampa", "NYY": "Bronx"}
        a = affected_games(s, d, teams_city)
        assert {g.game_pk for g in a} == {1, 2}


# ====================================================================
# repair_local: Standard-Faelle
# ====================================================================

class TestRepairLocalBasics:
    def test_disruption_outside_season_means_no_change(self):
        s = _mk_season([_g(1, 0, "NYY", "BOS"), _g(2, 1, "NYY", "BOS")])
        # Disruption ausserhalb der Saison — keine Spiele betroffen
        d = StadiumBlackout(
            home_team="NYY",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 5),
        )
        new_s, changes, unresched = repair_local(s, d)
        assert len(changes) == 0
        assert len(unresched) == 0
        assert len(new_s.games) == 2

    def test_single_game_postponed_to_next_free_day(self):
        # NYY hat Spiele an Tag 0 und 2; Tag 1 ist frei
        # Disruption an Tag 0: Spiel sollte auf Tag 1 verschoben werden
        s = _mk_season([
            _g(1, 0, "NYY", "BOS"),
            _g(2, 2, "NYY", "BOS"),
        ])
        d = StadiumBlackout(
            home_team="NYY",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 1),
        )
        new_s, changes, unresched = repair_local(s, d)
        assert len(changes) == 1
        assert len(unresched) == 0
        # Spiel 1 verschoben
        moved = next(g for g in new_s.games if g.game_pk == 1)
        assert moved.date == date(2026, 4, 2)

    def test_skips_days_with_existing_games_for_either_team(self):
        # NYY hat Spiele an Tag 0, 1, 2, 3, 4 (dicht gepackt)
        # Tag 5 ist frei
        s = _mk_season([
            _g(1, 0, "NYY", "BOS"),
            _g(2, 1, "NYY", "BOS"),
            _g(3, 2, "NYY", "BOS"),
            _g(4, 3, "NYY", "TOR"),
            _g(5, 4, "NYY", "TOR"),
        ])
        d = StadiumBlackout(
            home_team="NYY",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 1),
        )
        new_s, changes, unresched = repair_local(s, d)
        assert len(unresched) == 0
        moved = next(g for g in new_s.games if g.game_pk == 1)
        # Tag 5 = 2026-04-06 (Tag-Offset 5)
        assert moved.date == date(2026, 4, 6)

    def test_blackout_window_not_used_as_slot(self):
        # 3 Spiele an Tag 0, 1, 2 — Blackout deckt 0–4 ab
        # Naechster Slot ist Tag 5
        s = _mk_season([
            _g(1, 0, "NYY", "BOS"),
            _g(2, 1, "NYY", "BOS"),
            _g(3, 2, "NYY", "BOS"),
        ])
        d = StadiumBlackout(
            home_team="NYY",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 5),
        )
        new_s, changes, unresched = repair_local(s, d)
        # alle drei verschoben
        assert len(changes) == 3
        assert len(unresched) == 0
        # alle drei NACH dem Blackout
        for c in changes:
            assert c.new_date >= date(2026, 4, 6)

    def test_unreschedulable_when_no_slot_available(self):
        # Saison nur 2 Tage, beide blackout, kein Slot ueberhaupt
        s = _mk_season([_g(1, 0, "NYY", "BOS")], end_offset=1)
        d = StadiumBlackout(
            home_team="NYY",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 2),
        )
        new_s, changes, unresched = repair_local(s, d)
        assert len(unresched) == 1
        assert len(changes) == 0

    def test_unreschedulable_game_kept_in_season(self):
        """M5 (Sprint 2.10): Unreschedulable Spiele bleiben in der Saison
        (Game-Count konstant), statt still gelöscht zu werden."""
        s = _mk_season([_g(1, 0, "NYY", "BOS")], end_offset=1)
        d = StadiumBlackout(
            home_team="NYY",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 2),
        )
        new_s, changes, unresched = repair_local(s, d)
        assert len(unresched) == 1
        # Game-Count bleibt erhalten — das Spiel ist weiterhin in der Saison.
        assert len(new_s.games) == len(s.games)
        assert any(g.game_pk == 1 for g in new_s.games)

    def test_changes_are_deterministic(self):
        s = _mk_season([_g(1, 0, "NYY", "BOS"), _g(2, 3, "NYY", "BOS")])
        d = StadiumBlackout(
            home_team="NYY",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 1),
        )
        r1 = repair_local(s, d)
        r2 = repair_local(s, d)
        assert [c.new_date for c in r1[1]] == [c.new_date for c in r2[1]]


# ====================================================================
# Review-Fix P0-3 (2026-06-10): V(C)(12)-Limits im Slot-Finder
# ====================================================================

class TestVC12StreakGuard:
    """repair_local darf beim Verlegen keine konsekutive Spieltag-Folge
    > 20 (bzw. > 24 im dokumentierten Fallback) erzeugen — CBA V(C)(12).
    Repro des Review-Befunds: NYY-Blackout 2024 erzeugte vorher einen
    25-Tage-Streak (docs/REVIEW_2026-06-10_INDEPENDENT_AI.md, P0-3)."""

    def test_no_new_streak_over_20_synthetic(self):
        # NYY spielt Tag 0..19 durchgehend (20er-Streak, am Limit) gegen
        # rotierende Gegner; ein verlegtes Spiel darf NICHT an Tag 20
        # angedockt werden (waere Streak 21), sondern muss weiter springen.
        opps = ["BOS", "TBR", "TOR", "BAL"]
        games = [_g(i + 1, i, "NYY", opps[i % 4]) for i in range(20)]
        # Das zu verlegende Spiel an Tag 30 (Blackout trifft es):
        games.append(_g(99, 30, "NYY", "BOS"))
        s = _mk_season(games, end_offset=60)
        bl = StadiumBlackout(home_team="NYY",
                             start_date=date(2026, 5, 1),   # Tag 30
                             end_date=date(2026, 5, 1))
        new, changes, unres = repair_local(s, bl)
        assert len(changes) == 1
        from src.player_fatigue import max_games_without_off_day
        assert max_games_without_off_day(new, "NYY") <= 20
        # Tag 20 (2026-04-21) waere der naechste freie Tag — verboten:
        assert changes[0].new_date != date(2026, 4, 21)

    def test_real_2024_nyy_blackout_keeps_vc12(self):
        # Exakter Review-Repro: vorher 25-Tage-Streak, jetzt <= 20 und
        # keine neuen AC-2.1.9-Verstoesse.
        from src.datasources.local_file import LocalFileAdapter
        from src.player_fatigue import (all_teams_pass_fatigue_constraints,
                                        max_games_without_off_day)
        real = LocalFileAdapter(base_dir="data").fetch_season_schedule(2024)
        teams = sorted({g.home for g in real.games})
        bl = StadiumBlackout(home_team="NYY", start_date=date(2024, 8, 5),
                             end_date=date(2024, 8, 18), reason="Repro P0-3")
        new, changes, unres = repair_local(real, bl)
        ok, viols = all_teams_pass_fatigue_constraints(new, teams)
        assert ok, viols
        assert max_games_without_off_day(new, "NYY") <= 20
