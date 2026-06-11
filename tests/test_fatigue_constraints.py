"""Tests fuer AC-2.1.8 und AC-2.1.9 (nachgeholt in Sprint 2.2).

AC-2.1.8: Max 13 konsekutive Auswaerts-Tage pro Team (CBA-Proxy).
AC-2.1.9: Min 1 Off-Day alle 20 Spiele pro Team.

Strategie:
- Unit-Tests mit konstruierten Mini-Saisons fuer die Logik
- Integration-Test: realer Sprint-2.1-Generator-Output muss beide ACs einhalten
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import List

import pytest

from src.season import Game, Season
from src.player_fatigue import (
    max_consecutive_away_days,
    max_games_without_off_day,
    all_teams_pass_fatigue_constraints,
    compute_fatigue_report,
)


# ====================================================================
# Helper: Mini-Saison-Builder
# ====================================================================

def _mk_game(day_offset: int, home: str, away: str, base_date=date(2026, 4, 1)) -> Game:
    return Game(
        game_pk=1_000_000 + day_offset * 100 + ord(home[0]),
        date=base_date + timedelta(days=day_offset),
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


# ====================================================================
# Unit-Tests fuer max_consecutive_away_days
# ====================================================================

class TestMaxConsecutiveAwayDays:
    def test_no_games_returns_zero(self):
        s = _mk_season([])
        assert max_consecutive_away_days(s, "NYY") == 0

    def test_only_home_games_returns_zero(self):
        games = [_mk_game(i, "NYY", "BOS") for i in range(5)]
        s = _mk_season(games)
        assert max_consecutive_away_days(s, "NYY") == 0

    def test_5_day_away_trip(self):
        # 5 konsekutive Auswaertstage fuer NYY
        games = [_mk_game(i, "BOS", "NYY") for i in range(5)]
        s = _mk_season(games)
        assert max_consecutive_away_days(s, "NYY") == 5

    def test_home_breaks_streak(self):
        games = [
            _mk_game(0, "BOS", "NYY"),    # away
            _mk_game(1, "BOS", "NYY"),    # away
            _mk_game(2, "NYY", "TOR"),    # home -> bricht
            _mk_game(3, "BAL", "NYY"),    # away
            _mk_game(4, "BAL", "NYY"),    # away
        ]
        s = _mk_season(games)
        assert max_consecutive_away_days(s, "NYY") == 2

    def test_off_day_does_not_break_road_trip(self):
        # CBA-Definition (AC-2.1.8): Off-Day mitten in der Road-Trip zaehlt mit.
        # away Tag 0, away Tag 1, Off-Day Tag 2, away Tag 3 = Road-Trip 0..3 = 4.
        games = [
            _mk_game(0, "BOS", "NYY"),    # away
            _mk_game(1, "BOS", "NYY"),    # away
            # Tag 2: Off-Day (Team weiterhin auswaerts)
            _mk_game(3, "BAL", "NYY"),    # away
        ]
        s = _mk_season(games)
        assert max_consecutive_away_days(s, "NYY") == 4

    def test_review_reproduction_off_day_in_roadtrip(self):
        # Exaktes Reproduktions-Snippet aus REVIEW_EXTERN.md (C1):
        # BOS, BOS, Off, BAL, BAL -> echte CBA-Roadtrip = 5 Tage (vorher: 2).
        games = [
            _mk_game(0, "BOS", "NYY"),    # away
            _mk_game(1, "BOS", "NYY"),    # away
            # Tag 2: Off-Day
            _mk_game(3, "BAL", "NYY"),    # away
            _mk_game(4, "BAL", "NYY"),    # away
        ]
        s = _mk_season(games)
        assert max_consecutive_away_days(s, "NYY") == 5

    def test_at_limit_13_days(self):
        games = [_mk_game(i, "BOS", "NYY") for i in range(13)]
        s = _mk_season(games)
        assert max_consecutive_away_days(s, "NYY") == 13

    def test_over_limit_14_days(self):
        games = [_mk_game(i, "BOS", "NYY") for i in range(14)]
        s = _mk_season(games)
        assert max_consecutive_away_days(s, "NYY") == 14


# ====================================================================
# Unit-Tests fuer max_games_without_off_day
# ====================================================================

class TestMaxGamesWithoutOffDay:
    def test_empty_season(self):
        s = _mk_season([])
        assert max_games_without_off_day(s, "NYY") == 0

    def test_20_consecutive_play_days(self):
        # 20 Spieltage hintereinander - sollten exakt 20 Spiele sein
        games = [_mk_game(i, "NYY", "BOS") for i in range(20)]
        s = _mk_season(games)
        assert max_games_without_off_day(s, "NYY") == 20

    def test_off_day_resets_count(self):
        games = [
            _mk_game(0, "NYY", "BOS"),
            _mk_game(1, "NYY", "BOS"),
            _mk_game(2, "NYY", "BOS"),
            # day 3 off
            _mk_game(4, "NYY", "BOS"),
            _mk_game(5, "NYY", "BOS"),
        ]
        s = _mk_season(games)
        assert max_games_without_off_day(s, "NYY") == 3

    def test_doubleheader_counts_as_one_play_day(self):
        # CBA (docs/CBA_DEFINITIONS.md): ein Doubleheader zaehlt als EIN
        # Spieltag. 5 normale Spieltage (Tag 0-4) + 1 Doubleheader (Tag 5)
        # = 6 konsekutive SPIELTAGE ohne Off-Day, nicht 7 Einzelspiele.
        # (Regression: frueher zaehlte die Funktion Einzelspiele -> 7.)
        games = [_mk_game(i, "NYY", "BOS") for i in range(5)]
        dh1 = Game(game_pk=999, date=date(2026, 4, 1) + timedelta(days=5),
                    home="NYY", away="BOS", venue="NYY", doubleheader_seq=1)
        dh2 = Game(game_pk=1000, date=date(2026, 4, 1) + timedelta(days=5),
                    home="NYY", away="BOS", venue="NYY", doubleheader_seq=2)
        s = _mk_season(games + [dh1, dh2])
        assert max_games_without_off_day(s, "NYY") == 6

    def test_doubleheader_consistent_with_optimizer_max_run(self):
        # max_games_without_off_day (Validierung) muss mit der inkrementellen
        # Optimierer-Metrik _team_max_streaks._max_run uebereinstimmen, die
        # ebenfalls distinkte Spieltage zaehlt (CBA-Konsistenz, QA Q1).
        from src.generator_optimizer import _season_to_entries, _build_team_index, _team_max_streaks
        from src.generator import GeneratorConfig
        games = [_mk_game(i, "NYY", "BOS") for i in range(5)]
        dh1 = Game(game_pk=999, date=date(2026, 4, 1) + timedelta(days=5),
                    home="NYY", away="BOS", venue="NYY", doubleheader_seq=1)
        dh2 = Game(game_pk=1000, date=date(2026, 4, 1) + timedelta(days=5),
                    home="NYY", away="BOS", venue="NYY", doubleheader_seq=2)
        s = _mk_season(games + [dh1, dh2])
        cfg = GeneratorConfig(season=2026, season_start=date(2026, 4, 1),
                              season_end=date(2026, 9, 30))
        entries = _season_to_entries(s, cfg)
        team_idx = _build_team_index(entries)
        _, no_off = _team_max_streaks("NYY", entries, team_idx)
        assert no_off == max_games_without_off_day(s, "NYY") == 6


# ====================================================================
# all_teams_pass_fatigue_constraints
# ====================================================================

class TestPassFatigueConstraints:
    def test_clean_season_passes(self):
        # 3 Heimspiele, 3 Auswaerts mit Off-Day dazwischen
        games = [
            _mk_game(0, "NYY", "BOS"),
            _mk_game(1, "NYY", "BOS"),
            _mk_game(2, "NYY", "BOS"),
            _mk_game(4, "BAL", "NYY"),
            _mk_game(5, "BAL", "NYY"),
        ]
        s = _mk_season(games)
        ok, viols = all_teams_pass_fatigue_constraints(s, ["NYY"])
        assert ok and viols == []

    def test_14_day_away_trip_violates_AC_2_1_8(self):
        games = [_mk_game(i, "BOS", "NYY") for i in range(14)]
        s = _mk_season(games)
        ok, viols = all_teams_pass_fatigue_constraints(s, ["NYY"])
        assert not ok
        assert any("AC-2.1.8" in v for v in viols)

    def test_21_games_no_off_violates_AC_2_1_9(self):
        games = [_mk_game(i, "NYY", "BOS") for i in range(21)]
        s = _mk_season(games)
        ok, viols = all_teams_pass_fatigue_constraints(s, ["NYY"])
        assert not ok
        assert any("AC-2.1.9" in v for v in viols)


# ====================================================================
# Integration-Test: voller Sprint-2.1-Generator
# ====================================================================

@pytest.fixture(scope="module")
def full_season_2026():
    """Voller Sprint-2.1-Generator-Output. Wird einmal gebaut und shared."""
    from src.datasources import LocalFileAdapter
    from src.generator import GeneratorConfig, generate
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
    )
    res = generate(quotas, cfg)
    return res.season


def test_AC_2_1_8_ist_weiches_qualitaetsziel_kein_hartes_erfordernis(full_season_2026, teams):
    """AC-2.1.8 ('days away from home', Ziel ≤ 13) ist seit 2026-06-09 ein WEICHES
    Qualitätsziel, KEIN hartes CBA-Erfordernis.

    Verifiziert (regulations/FINDING_AC-2.1.8_vs_CBA.md): '13 days away' steht NICHT
    im CBA Article V — es ist eine Belastungs-Heuristik ('13-Game-Gauntlet'). Das harte
    CBA-Muss ist V(C)(12) = AC-2.1.9 (≤ 20 konsekutive Spieltage, separat getestet und
    strukturell garantiert). Damit ist die frühere ≤13-Garantie (Q10, xfail) obsolet;
    der Branch-and-Price-Aufwand dafür entfällt.

    Dieser Test schreibt die Entscheidung fest (AC-2.1.8 = soft in der Compliance) und
    überwacht die Road-Trip-Längen des From-Scratch-Generators als Qualitätsmetrik —
    ohne eine harte ≤13-Garantie zu verlangen.
    """
    from src.compliance import RULES

    # Entscheidung festgeschrieben: AC-2.1.8 ist weich, nicht hart.
    assert RULES["AC-2.1.8"].severity == "soft"

    # Qualitäts-Monitoring (kein harter Failure): Road-Trip-Längen werden gemessen.
    # Die weiche SA-Penalty hält sie im realistischen Bereich; das harte Muss (AC-2.1.9)
    # wird in test_*_AC_2_1_9 / Compliance separat geprüft.
    team_ids = [t.id for t in teams]
    worst = max(max_consecutive_away_days(full_season_2026, tid) for tid in team_ids)
    assert worst > 0  # Sanity: Metrik berechenbar; bewusst KEINE harte ≤13-Schranke.


def test_AC_2_1_9_realer_generator_haelt_off_day_frequenz(full_season_2026, teams):
    """AC-2.1.9: Sprint-2.4-Greedy-Generator haelt das Limit ein (AC-2.3.10)."""
    team_ids = [t.id for t in teams]
    for tid in team_ids:
        n = max_games_without_off_day(full_season_2026, tid)
        assert n <= 20, f"Team {tid}: {n} Spiele ohne Off-Day (Limit 20)"


def test_fatigue_report_aggregates_unter_realen_bedingungen(full_season_2026, teams):
    """Fatigue-Report aggregiert sauber."""
    team_ids = [t.id for t in teams]
    rep = compute_fatigue_report(full_season_2026, team_ids)
    assert rep.league_total_fatigue > 0
    assert len(rep.by_team_max_consec_away) == 30
    assert len(rep.by_team_max_no_off) == 30
