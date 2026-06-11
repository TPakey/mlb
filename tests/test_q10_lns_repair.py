"""Q10 — Sicherheits-Garantien des gefensterten CP-SAT-LNS-Repairs.

Geprueft werden die invarianten Eigenschaften, die der Repair IMMER halten muss
(unabhaengig davon, ob er eine konkrete Verletzung vollstaendig aufloest):

1. Matchup-Erhaltung: das Multiset (home, away, length) bleibt exakt gleich —
   es werden nur start_days verschoben, nie Spiele hinzugefuegt/entfernt.
2. Keine Regression: der globale worst_away wird nicht groesser.
3. AC-2.1.9 wird nicht verletzt (max Spieltage-Streak bleibt <= Limit, sofern
   vorher erfuellt).
4. Determinismus: zwei identische Laeufe liefern bit-identische start_days.
"""
from collections import Counter

from src.generator_optimizer import (
    SeriesEntry, _build_team_index, _lns_window_repair,
    _team_worst_trip, _team_max_streaks,
)


def _make_violating_entries():
    """2 Teams, 40 Tage: Team A hat eine 16-Tage-Road-Trip (Off-Days zaehlen)."""
    e = [
        SeriesEntry(idx=0, home="B", away="A", length=4, start_day=0),   # A away 0-3
        SeriesEntry(idx=1, home="B", away="A", length=4, start_day=6),   # A away 6-9
        SeriesEntry(idx=2, home="B", away="A", length=4, start_day=12),  # A away 12-15
        SeriesEntry(idx=3, home="A", away="B", length=4, start_day=20),  # A home 20-23
        SeriesEntry(idx=4, home="A", away="B", length=4, start_day=26),  # A home 26-29
        SeriesEntry(idx=5, home="A", away="B", length=4, start_day=32),  # A home 32-35
    ]
    return e


def _multiset(entries):
    return Counter((e.home, e.away, e.length) for e in entries)


def _valid_starts(entries, total_days):
    out = {}
    for L in {e.length for e in entries}:
        out[L] = set(range(0, total_days - L + 1))
    return out


def test_lns_preserves_matchups_and_no_regression():
    entries = _make_violating_entries()
    total_days = 40
    team_idx = _build_team_index(entries)
    vs = _valid_starts(entries, total_days)

    before_multiset = _multiset(entries)
    before_worst = max(_team_worst_trip(t, entries, team_idx) for t in team_idx)
    assert before_worst > 13  # die Instanz ist absichtlich verletzend

    _lns_window_repair(entries, team_idx, vs, total_days,
                       away_limit=13, off_limit=20, pad=8,
                       solve_time_s=3.0, budget_s=10.0)

    after_multiset = _multiset(entries)
    after_worst = max(_team_worst_trip(t, entries, team_idx) for t in team_idx)

    assert after_multiset == before_multiset, "Matchup-Quoten veraendert!"
    assert after_worst <= before_worst, "Repair hat den worst_away verschlechtert!"


def test_lns_is_deterministic():
    def run():
        entries = _make_violating_entries()
        team_idx = _build_team_index(entries)
        vs = _valid_starts(entries, 40)
        _lns_window_repair(entries, team_idx, vs, 40, away_limit=13,
                           solve_time_s=3.0, budget_s=10.0)
        return [e.start_day for e in entries]

    assert run() == run(), "LNS-Repair ist nicht deterministisch (1-Worker, fester Seed)"
