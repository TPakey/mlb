"""Tests fuer Strategie C — Venue-Swap mit Revanche."""
from __future__ import annotations

from datetime import date, timedelta
from typing import List

import pytest

from src.disruption_types import StadiumBlackout
from src.repair_venue_swap import repair_venue_swap
from src.season import Game, Season


def _g(pk: int, day_offset: int, home: str, away: str) -> Game:
    return Game(
        game_pk=pk,
        date=date(2026, 4, 1) + timedelta(days=day_offset),
        home=home,
        away=away,
        venue=home,
    )


def _mk_season(games: List[Game]) -> Season:
    return Season(
        season=2026,
        games=games,
        season_start=date(2026, 4, 1),
        season_end=date(2026, 9, 30),
    )


class TestVenueSwapBasics:
    def test_swap_with_existing_counterpart(self):
        """NYY @ BOS am Tag 0 (=NYY home) wird betroffen.
        Counterpart: BOS @ NYY (=BOS home) am Tag 30.
        Erwartung: beide Spiele tauschen Heimrecht."""
        s = _mk_season([
            _g(1, 0, "NYY", "BOS"),    # NYY home, betroffen
            _g(2, 30, "BOS", "NYY"),   # BOS home, Counterpart
        ])
        d = StadiumBlackout(
            home_team="NYY",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 1),
        )
        new_s, changes, unresolved = repair_venue_swap(s, d)
        assert unresolved == []
        # Spiel 1: jetzt BOS home
        g1 = next(g for g in new_s.games if g.game_pk == 1)
        assert g1.home == "BOS" and g1.away == "NYY"
        # Spiel 2: jetzt NYY home
        g2 = next(g for g in new_s.games if g.game_pk == 2)
        assert g2.home == "NYY" and g2.away == "BOS"
        # Daten unveraendert
        assert g1.date == date(2026, 4, 1)
        assert g2.date == date(2026, 5, 1)
        # 2 swap-Changes
        assert len(changes) == 2
        assert all(c.change_type == "swap" for c in changes)

    def test_no_counterpart_is_unresolvable(self):
        s = _mk_season([
            _g(1, 0, "NYY", "BOS"),    # NYY home, betroffen
            _g(2, 30, "NYY", "BOS"),   # KEIN counterpart (gleiches Heimrecht)
        ])
        d = StadiumBlackout(
            home_team="NYY",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 1),
        )
        new_s, changes, unresolved = repair_venue_swap(s, d)
        assert len(unresolved) == 1
        assert len(changes) == 0

    def test_home_away_balance_preserved(self):
        """Heim/Auswaerts-Bilanz pro Team bleibt unveraendert."""
        s = _mk_season([
            _g(1, 0, "NYY", "BOS"),    # NYY home
            _g(2, 30, "BOS", "NYY"),
        ])
        d = StadiumBlackout(
            home_team="NYY",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 1),
        )
        new_s, changes, unresolved = repair_venue_swap(s, d)
        # NYY: vorher 1 home, 1 away — danach: 1 home, 1 away (anderes Spiel)
        nyy_home = sum(1 for g in new_s.games if g.home == "NYY")
        nyy_away = sum(1 for g in new_s.games if g.away == "NYY")
        assert nyy_home == 1 and nyy_away == 1
        bos_home = sum(1 for g in new_s.games if g.home == "BOS")
        bos_away = sum(1 for g in new_s.games if g.away == "BOS")
        assert bos_home == 1 and bos_away == 1

    def test_uses_earliest_counterpart_deterministically(self):
        """Bei mehreren Counterparts wird der zeitlich naechstgelegene gewaehlt."""
        s = _mk_season([
            _g(1, 0, "NYY", "BOS"),     # betroffen
            _g(2, 30, "BOS", "NYY"),    # cp 1 (sollte gewaehlt werden)
            _g(3, 60, "BOS", "NYY"),    # cp 2
        ])
        d = StadiumBlackout(
            home_team="NYY",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 1),
        )
        new_s, changes, unresolved = repair_venue_swap(s, d)
        # Spiel 2 ist getauscht, Spiel 3 unveraendert
        g2 = next(g for g in new_s.games if g.game_pk == 2)
        g3 = next(g for g in new_s.games if g.game_pk == 3)
        assert g2.home == "NYY"     # getauscht
        assert g3.home == "BOS"     # unveraendert

    def test_partial_when_more_affected_than_counterparts(self):
        """Mehrere affected-Spiele, weniger Counterparts: rest in unresolvable."""
        s = _mk_season([
            _g(1, 0, "NYY", "BOS"),
            _g(2, 1, "NYY", "BOS"),
            _g(3, 2, "NYY", "BOS"),
            _g(4, 30, "BOS", "NYY"),   # nur 1 cp
        ])
        d = StadiumBlackout(
            home_team="NYY",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 3),
        )
        new_s, changes, unresolved = repair_venue_swap(s, d)
        assert len(unresolved) == 2
        assert len(changes) == 2   # 1 swap + 1 counterpart-swap
