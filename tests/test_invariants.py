"""Property-based Tests (hypothesis) — invariante Eigenschaften (Sprint 2.12).

Testet schnelle, reine Funktionen gegen Invarianten über viele zufällige
Eingaben — kein voller Generator-Run (zu langsam für 200 Examples).
"""
from __future__ import annotations

from datetime import date, timedelta

from hypothesis import given, settings, strategies as st

from src.season import Game, Season
from src.player_fatigue import max_consecutive_away_days
from src.generator_optimizer import (
    SeriesEntry, _build_team_index, _team_max_streaks, _team_worst_trip,
    _greedy_fatigue_repair,
)
from src.tv_slots import TvSlotConfig
from src.distance import tz_offset_hours, TIMEZONE_OFFSET

BASE = date(2026, 4, 1)

# Eine Strategie für nicht-überlappende Serien (start_day, length, is_away) eines Teams.
@st.composite
def _team_layout(draw):
    n = draw(st.integers(min_value=1, max_value=8))
    layout = []
    cursor = 0
    for _ in range(n):
        gap = draw(st.integers(min_value=0, max_value=4))   # Off-Days dazwischen
        length = draw(st.integers(min_value=1, max_value=4))
        is_away = draw(st.booleans())
        start = cursor + gap
        layout.append((start, length, is_away))
        cursor = start + length
    return layout


def _entries_from_layout(layout):
    entries = []
    for i, (start, length, is_away) in enumerate(layout):
        home = "OPP" if is_away else "NYY"
        away = "NYY" if is_away else "OPP"
        entries.append(SeriesEntry(idx=i, home=home, away=away,
                                   length=length, start_day=start))
    return entries


def _season_from_layout(layout) -> Season:
    games = []
    pk = 1
    for (start, length, is_away) in layout:
        for off in range(length):
            d = BASE + timedelta(days=start + off)
            if is_away:
                games.append(Game(pk, d, "OPP", "NYY", "OPP"))
            else:
                games.append(Game(pk, d, "NYY", "OPP", "NYY"))
            pk += 1
    return Season(season=2026, games=games, season_start=BASE,
                  season_end=BASE + timedelta(days=120))


class TestAc218Consistency:
    @settings(max_examples=200)
    @given(_team_layout())
    def test_two_implementations_agree(self, layout):
        """player_fatigue.max_consecutive_away_days == generator_optimizer._team_max_streaks
        (away-Komponente) für denselben Plan."""
        season = _season_from_layout(layout)
        entries = _entries_from_layout(layout)
        ti = _build_team_index(entries)
        from_pf = max_consecutive_away_days(season, "NYY")
        from_sa, _ = _team_max_streaks("NYY", entries, ti)
        assert from_pf == from_sa

    @settings(max_examples=200)
    @given(_team_layout())
    def test_away_streak_nonnegative_and_bounded(self, layout):
        season = _season_from_layout(layout)
        worst = max_consecutive_away_days(season, "NYY")
        span = max((s + l) for s, l, _ in layout)
        assert 0 <= worst <= span


class TestRepairMonotone:
    @settings(max_examples=150)
    @given(_team_layout())
    def test_repair_never_creates_new_violation(self, layout):
        """Korrigierter Repair-Vertrag (Sprint A-6): Wenn eine Partner-Mannschaft
        durch einen akzeptierten Swap betroffen wird, darf ihr Worst-Trip
        wachsen — aber NUR bis ``max(away_limit, pre[partner])``. Insbesondere
        gilt: war eine Mannschaft VOR dem Repair unter dem Limit, ist sie es
        auch DANACH. Die fruehere Invariante ``after <= before`` war zu streng
        und wurde von hypothesis korrekt als Counter-Beispiel entlarvt."""
        away_limit = 5
        entries = _entries_from_layout(layout)
        ti = _build_team_index(entries)
        before = _team_worst_trip("NYY", entries, ti)
        _greedy_fatigue_repair(entries, ti,
                               {l: set(range(0, 200)) for l in range(1, 5)},
                               away_limit=away_limit)
        after = _team_worst_trip("NYY", entries, ti)
        # Repair-Garantie: keine NEUE Verletzung. Wer drunter war, bleibt drunter.
        if before <= away_limit:
            assert after <= away_limit


class TestTvAndTz:
    @settings(max_examples=50)
    @given(st.integers(min_value=0, max_value=6))
    def test_expected_slot_within_day_night_bounds(self, wd):
        cfg = TvSlotConfig.load()
        ev = cfg.expected_slot_value(wd)
        lo = min(cfg.slot_value(wd, "day"), cfg.slot_value(wd, "night"))
        hi = max(cfg.slot_value(wd, "day"), cfg.slot_value(wd, "night"))
        assert lo - 1e-9 <= ev <= hi + 1e-9

    @settings(max_examples=100)
    @given(st.sampled_from(sorted(TIMEZONE_OFFSET)),
           st.integers(min_value=0, max_value=364))
    def test_tz_offset_in_plausible_range(self, tz, day_offset):
        d = date(2026, 1, 1) + timedelta(days=day_offset)
        off = tz_offset_hours(tz, d)
        # USA-Zeitzonen: zwischen -8 (PST) und -4 (EDT).
        assert -8 <= off <= -4
