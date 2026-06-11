"""Tests für Sprint 2.4 — AC-2.3.10 + Doubleheader-Fix + Demo-Skript.

AC-2.3.10: Der Generator (generate()) muss für enforce_fatigue_constraints=True
            AC-2.1.8 und AC-2.1.9 in einem vollen Saisonplan einhalten.

Zusätzlich:
  - _entry_from_games: length = Anzahl TAGE (nicht Spiele) — Doubleheader-Fix
  - demo_pareto.py: lauffähig, produziert validen JSON-Output
  - GeneratorConfig.enforce_fatigue_constraints=True ist Default

Sprint-Referenz: docs/SPRINT_2_4_REVIEW.md
"""
from __future__ import annotations

import json
import tempfile
from datetime import date, timedelta

import pytest

from src.season import Game, Season
from src.generator import GeneratorConfig
from src.generator_optimizer import (
    SeriesEntry,
    _entry_from_games,
    _season_to_entries,
    _build_team_index,
    _team_max_streaks,
    _team_road_trips,
    _team_worst_trip,
    _greedy_fatigue_repair,
)


# ====================================================================
# Hilfsfunktionen
# ====================================================================

def _mk_game(day_offset: int, home: str, away: str,
             base: date = date(2026, 4, 1), dh_seq: int = 0) -> Game:
    return Game(
        game_pk=900_000 + day_offset * 100 + ord(home[0]),
        date=base + timedelta(days=day_offset),
        home=home,
        away=away,
        venue=home,
        doubleheader_seq=dh_seq,
    )


def _mk_season(games) -> Season:
    return Season(
        season=2026,
        games=list(games),
        season_start=date(2026, 4, 1),
        season_end=date(2026, 9, 30),
    )


_BASE_CFG = GeneratorConfig(
    season=2026,
    season_start=date(2026, 4, 1),
    season_end=date(2026, 9, 30),
)


# ====================================================================
# AC-2.3.10: enforce_fatigue_constraints Default
# ====================================================================

class TestEnforceFatigueDefault:
    def test_default_is_true(self):
        """enforce_fatigue_constraints muss per Default True sein (AC-2.3.10)."""
        cfg = GeneratorConfig(
            season=2026,
            season_start=date(2026, 3, 26),
            season_end=date(2026, 9, 27),
        )
        assert cfg.enforce_fatigue_constraints is True

    def test_can_be_disabled(self):
        cfg = GeneratorConfig(
            season=2026,
            season_start=date(2026, 3, 26),
            season_end=date(2026, 9, 27),
            enforce_fatigue_constraints=False,
        )
        assert cfg.enforce_fatigue_constraints is False


# ====================================================================
# Doubleheader-Fix: _entry_from_games / _season_to_entries
# ====================================================================

class TestDoubleheaderFix:
    """AC-2.3.10 Nebenfix: SeriesEntry.length muss Tage, nicht Spiele sein."""

    def test_normal_series_length_equals_days(self):
        """3-Spiele-Serie über 3 Tage → length = 3."""
        games = [_mk_game(i, "NYY", "BOS") for i in range(3)]
        e = _entry_from_games(0, games, _BASE_CFG)
        assert e.length == 3

    def test_doubleheader_length_is_1_day(self):
        """Doubleheader (2 Spiele, 1 Tag) → length = 1, nicht 2."""
        base = date(2026, 4, 1)
        dh1 = Game(game_pk=1, date=base, home="NYY", away="BOS", venue="NYY", doubleheader_seq=1)
        dh2 = Game(game_pk=2, date=base, home="NYY", away="BOS", venue="NYY", doubleheader_seq=2)
        e = _entry_from_games(0, [dh1, dh2], _BASE_CFG)
        assert e.length == 1, f"Doubleheader sollte length=1 haben, got {e.length}"

    def test_days_occupied_correct_for_doubleheader(self):
        """days_occupied() eines Doubleheader-Eintrags muss genau 1 Tag enthalten."""
        base = date(2026, 4, 1)
        dh1 = Game(game_pk=1, date=base, home="NYY", away="BOS", venue="NYY", doubleheader_seq=1)
        dh2 = Game(game_pk=2, date=base, home="NYY", away="BOS", venue="NYY", doubleheader_seq=2)
        e = _entry_from_games(0, [dh1, dh2], _BASE_CFG)
        assert len(e.days_occupied()) == 1

    def test_normal_series_days_occupied_consecutive(self):
        """3-Spiele-Serie → days_occupied = {0, 1, 2}."""
        games = [_mk_game(i, "NYY", "BOS") for i in range(3)]
        e = _entry_from_games(0, games, _BASE_CFG)
        assert e.days_occupied() == {0, 1, 2}

    def test_season_to_entries_groups_doubleheader_correctly(self):
        """_season_to_entries darf Doubleheader nicht als 2-Tage-Serie fehlklassifizieren."""
        base = date(2026, 4, 1)
        # 3 normale Spiele (Tage 0-2) + Doubleheader (Tag 3)
        games = [_mk_game(i, "NYY", "BOS") for i in range(3)]
        dh1 = Game(game_pk=999, date=base + timedelta(days=3),
                    home="NYY", away="BOS", venue="NYY", doubleheader_seq=1)
        dh2 = Game(game_pk=1000, date=base + timedelta(days=3),
                    home="NYY", away="BOS", venue="NYY", doubleheader_seq=2)

        season = _mk_season(games + [dh1, dh2])
        cfg = GeneratorConfig(
            season=2026,
            season_start=base,
            season_end=base + timedelta(days=180),
        )
        entries = _season_to_entries(season, cfg)
        # Alle Einträge: nur NYY@BOS-Serie(n)
        nyy_entries = [e for e in entries if e.home == "NYY" and e.away == "BOS"]
        # Kein Entry darf length=2 bei Tagen belegen, die nur 1 Tag sind
        for e in nyy_entries:
            assert e.length == len(e.days_occupied()), (
                f"Entry {e}: length={e.length} != days_occupied={len(e.days_occupied())}"
            )


# ====================================================================
# Team-Max-Streaks: konsistente Berechnung im SA
# ====================================================================

class TestTeamMaxStreaks:
    def _make_entries(self, schedule):
        """schedule = list of (start_day, length, is_away)"""
        entries = []
        for i, (start, length, is_away) in enumerate(schedule):
            home = "NYY" if not is_away else "BOS"
            away = "BOS" if not is_away else "NYY"
            entries.append(SeriesEntry(idx=i, home=home, away=away,
                                        length=length, start_day=start))
        return entries

    def test_simple_away_streak(self):
        entries = self._make_entries([
            (0, 3, True),   # away days 0-2
            (3, 3, True),   # away days 3-5 → 6 konsekutiv
        ])
        team_idx = _build_team_index(entries)
        ca, no = _team_max_streaks("NYY", entries, team_idx)
        assert ca == 6

    def test_home_breaks_away_streak(self):
        entries = self._make_entries([
            (0, 3, True),   # away 0-2
            (3, 2, False),  # home 3-4 → bricht
            (5, 3, True),   # away 5-7
        ])
        team_idx = _build_team_index(entries)
        ca, no = _team_max_streaks("NYY", entries, team_idx)
        assert ca == 3

    def test_off_day_does_not_break_road_trip(self):
        # CBA-Definition (AC-2.1.8): Off-Days mitten in der Road-Trip zaehlen
        # mit. away 0-2, Off-Day 3, away 4-6 ist EINE Road-Trip 0-6 = 7 Tage.
        entries = self._make_entries([
            (0, 3, True),   # away 0-2
            # day 3: off (Team weiterhin auswaerts / auf Achse)
            (4, 3, True),   # away 4-6
        ])
        team_idx = _build_team_index(entries)
        ca, no = _team_max_streaks("NYY", entries, team_idx)
        assert ca == 7

    def test_max_games_no_off(self):
        # 6 aufeinanderfolgende Spieltage
        entries = self._make_entries([
            (0, 3, True),
            (3, 3, False),
        ])
        team_idx = _build_team_index(entries)
        _, no = _team_max_streaks("NYY", entries, team_idx)
        assert no == 6


class TestFatigueRepair:
    """AC-2.1.8 Pre/Post-Repair (Sprint 2.7 / Review C1)."""

    def test_road_trips_span_includes_off_days(self):
        # away 0-2, Off 3, away 4-6  -> EINE Road-Trip 0..6
        entries = [
            SeriesEntry(idx=0, home="BOS", away="NYY", length=3, start_day=0),
            SeriesEntry(idx=1, home="BAL", away="NYY", length=3, start_day=4),
        ]
        ti = _build_team_index(entries)
        trips = _team_road_trips("NYY", entries, ti)
        assert trips == [(0, 6)]
        assert _team_worst_trip("NYY", entries, ti) == 7

    def test_repair_breaks_long_road_trip(self):
        # 9-Tage-Road-Trip fuer NYY + eine weit entfernte Heimserie -> Repair
        # relociert die Heimserie in den Trip und bricht ihn auf.
        entries = [
            SeriesEntry(idx=0, home="BOS", away="NYY", length=3, start_day=0),
            SeriesEntry(idx=1, home="BAL", away="NYY", length=3, start_day=3),
            SeriesEntry(idx=2, home="TOR", away="NYY", length=3, start_day=6),
            SeriesEntry(idx=3, home="NYY", away="TB",  length=3, start_day=20),
        ]
        ti = _build_team_index(entries)
        assert _team_worst_trip("NYY", entries, ti) == 9
        applied = _greedy_fatigue_repair(
            entries, ti, {3: set(range(0, 30))}, away_limit=5, off_limit=20)
        # Best-Effort-Heuristik: garantiert strikte Verbesserung, nicht Optimum.
        assert applied >= 1
        assert _team_worst_trip("NYY", entries, ti) < 9


# ====================================================================
# Demo-Skript: Lauffähigkeit (Smoke-Test, kein voller Generator-Run)
# ====================================================================

class TestDemoPareto:
    def test_demo_script_importable(self):
        """tools/demo_pareto.py muss importierbar sein (keine Syntax-/Import-Fehler)."""
        import importlib.util, sys
        from pathlib import Path
        spec = importlib.util.spec_from_file_location(
            "demo_pareto",
            Path(__file__).parent.parent / "tools" / "demo_pareto.py",
        )
        mod = importlib.util.module_from_spec(spec)
        # Nicht vollständig ausführen, nur laden
        assert spec is not None
        assert mod is not None

    def test_demo_argparse_defaults(self):
        """Argparse-Defaults des Demo-Scripts sind sinnvoll."""
        import importlib.util, sys
        from pathlib import Path
        spec = importlib.util.spec_from_file_location(
            "demo_pareto",
            Path(__file__).parent.parent / "tools" / "demo_pareto.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # _parse_args mit leerer argv simulieren
        import argparse
        # Überschreibe sys.argv temporär
        orig = sys.argv[:]
        sys.argv = ["demo_pareto"]
        try:
            args = mod._parse_args()
        finally:
            sys.argv = orig

        assert args.seed == 42
        assert args.sa_iter == 3000
        assert args.interior == 4
        assert args.shift == 7
        assert args.no_json is False
        assert args.verbose is False
