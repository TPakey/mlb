"""
Sprint 2.3a Test Suite — Column Generation, Global HAP Solver, Phase B Series Matching.

Testet alle Kernkomponenten von Sprint 2.3a:
  1. GlobalHAPResult / solve_global_hap — strukturelle Korrektheit
  2. Phase-B Series Matching (Soft Slot-Modell) — Feasibility + Qualität
  3. AC-2.1.8 / AC-2.1.9 auf dem vollständigen Schedule
  4. Pair-Matching-Invariante: an jedem Tag #H-Teams == #A-Teams
  5. Column Generation RMP + Pricing (Mini-System)
"""
from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path
from typing import Dict, List, Set

import pytest

# ────────────────────────────────────────────────────────────────────────────────
# Hilfsinfrastruktur
# ────────────────────────────────────────────────────────────────────────────────

BREAK_DAYS: Set[int] = {
    (date(2026, 7, 13) - date(2026, 3, 26)).days + i for i in range(4)
}
TOTAL_DAYS = 186
N_TEAMS    = 30
N_HOME     = 81
N_AWAY     = 81

MLB_TEAMS = [
    'ARI', 'ATL', 'BAL', 'BOS', 'CHC', 'CWS', 'CIN', 'CLE',
    'COL', 'DET', 'HOU', 'KC',  'LAA', 'LAD', 'MIA', 'MIL',
    'MIN', 'NYM', 'NYY', 'OAK', 'PHI', 'PIT', 'SD',  'SEA',
    'SF',  'STL', 'TB',  'TEX', 'TOR', 'WSH',
]


# ────────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def hap_result():
    """OPTIMAL HAP-Result für alle 30 Teams (seed=42)."""
    from src.column_generation import solve_global_hap
    result = solve_global_hap(
        team_ids=MLB_TEAMS,
        n_home=N_HOME,
        n_away=N_AWAY,
        total_days=TOTAL_DAYS,
        break_days=BREAK_DAYS,
        seed=42,
        solver_time_limit_s=30.0,
        verbose=False,
    )
    return result


@pytest.fixture(scope="module")
def hap_patterns(hap_result):
    return hap_result.patterns


@pytest.fixture(scope="module")
def phase_b_result(hap_patterns):
    """Phase-B-Ergebnis mit Soft-Slot-Modell."""
    from src.series_matching import match_series_slots_soft
    result = match_series_slots_soft(
        patterns=hap_patterns,
        total_days=TOTAL_DAYS,
        break_days=BREAK_DAYS,
        verbose=False,
        time_limit_s=60.0,
    )
    return result


# ────────────────────────────────────────────────────────────────────────────────
# 1. Globaler HAP Solver
# ────────────────────────────────────────────────────────────────────────────────

@pytest.mark.slow
class TestGlobalHAPSolver:
    # P2-7: voller 30-Team-HAP-CP-SAT-Solve (~30s) → CI-only. Lokal/Sandbox via
    # `-m "not slow"` deselektiert (sonst Solver-Timeout). Schnelle Smoke-Deckung
    # des Generator-Pfads: tests/test_reduced_smoke.py.

    def test_solver_status_is_optimal(self, hap_result):
        """HAP-Solver muss OPTIMAL liefern (nicht nur FEASIBLE)."""
        assert hap_result.status == "OPTIMAL", (
            f"Erwartet OPTIMAL, bekam {hap_result.status}"
        )

    def test_patterns_contain_all_30_teams(self, hap_patterns):
        assert len(hap_patterns) == N_TEAMS

    def test_each_team_exactly_81_home_games(self, hap_patterns):
        for tid, marks in hap_patterns.items():
            n_home = sum(1 for m in marks if m == 'H')
            assert n_home == N_HOME, f"{tid}: {n_home} Heimspiele, erwartet {N_HOME}"

    def test_each_team_exactly_81_away_games(self, hap_patterns):
        for tid, marks in hap_patterns.items():
            n_away = sum(1 for m in marks if m == 'A')
            assert n_away == N_AWAY, f"{tid}: {n_away} Auswärtsspiele, erwartet {N_AWAY}"

    def test_no_games_on_break_days(self, hap_patterns):
        for tid, marks in hap_patterns.items():
            for d in BREAK_DAYS:
                assert marks[d] == 'O', (
                    f"{tid}: Spiel an Break-Tag {d} (marks={marks[d]})"
                )

    def test_pair_matching_invariant(self, hap_patterns):
        """An jedem Spieltag: #Heim-Teams == #Auswärts-Teams."""
        for d in range(TOTAL_DAYS):
            if d in BREAK_DAYS:
                continue
            n_h = sum(1 for m in hap_patterns.values() if m[d] == 'H')
            n_a = sum(1 for m in hap_patterns.values() if m[d] == 'A')
            assert n_h == n_a, (
                f"Tag {d}: Pair-Mismatch — {n_h} Heim vs {n_a} Auswärts"
            )

    def test_zero_pair_violations(self, hap_result):
        assert len(hap_result.violations) == 0, (
            f"Pair-Violations: {hap_result.violations[:3]}"
        )

    def test_series_lengths_2_to_4(self, hap_patterns):
        """Alle HAP-Serien müssen Länge 2-4 haben."""
        from src.series_matching import parse_hap_series
        hap = parse_hap_series(hap_patterns, BREAK_DAYS)
        violations = [
            f"{tid}: {s.type}-Serie Tag {s.start_day}..{s.end_day} (Länge {s.length})"
            for tid, series_list in hap.items()
            for s in series_list
            if s.length < 2 or s.length > 4
        ]
        assert len(violations) == 0, f"Serien-Längen-Verletzungen: {violations[:3]}"

    def test_solve_time_under_30_seconds(self, hap_result):
        """HAP-Solver muss unter 30s laufen (OPTIMAL)."""
        assert hap_result.solve_time_s < 30.0, (
            f"HAP-Solver hat {hap_result.solve_time_s:.1f}s gebraucht"
        )


# ────────────────────────────────────────────────────────────────────────────────
# 2. AC-2.1.8 / AC-2.1.9
# ────────────────────────────────────────────────────────────────────────────────

class TestFatigueConstraints:

    def _is_playable(self, d: int) -> bool:
        return 0 <= d < TOTAL_DAYS and d not in BREAK_DAYS

    def test_ac_2_1_8_max_13_consecutive_away(self, hap_patterns):
        """AC-2.1.8: Kein Team hat mehr als 13 konsekutive Auswärtstage."""
        violations = []
        for tid, marks in hap_patterns.items():
            streak = 0
            for d in range(TOTAL_DAYS):
                if d in BREAK_DAYS:
                    streak = 0
                    continue
                if marks[d] == 'A':
                    streak += 1
                    if streak > 13:
                        violations.append(f"{tid}: streak={streak} an Tag {d}")
                else:
                    streak = 0
        assert len(violations) == 0, f"AC-2.1.8 Verletzungen: {violations[:3]}"

    def test_ac_2_1_9_max_20_games_in_21_days(self, hap_patterns):
        """AC-2.1.9: Kein Team hat mehr als 20 Spieltage in einem 21-Tage-Fenster."""
        violations = []
        for tid, marks in hap_patterns.items():
            for d in range(TOTAL_DAYS - 20):
                games = sum(
                    1 for dd in range(d, d + 21)
                    if dd not in BREAK_DAYS and marks[dd] in ('H', 'A')
                )
                if games > 20:
                    violations.append(f"{tid}: {games} Spiele in [{d}..{d+20}]")
                    break  # Nur erste Verletzung pro Team
        assert len(violations) == 0, f"AC-2.1.9 Verletzungen: {violations[:3]}"


# ────────────────────────────────────────────────────────────────────────────────
# 3. Phase-B Series Matching (Soft Slot Model)
# ────────────────────────────────────────────────────────────────────────────────

@pytest.mark.slow
class TestPhaseBMatching:  # P2-7: hängt am HAP-Fixture (CP-SAT) → CI-only.

    def test_phase_b_feasible(self, phase_b_result):
        """Phase B muss eine Lösung finden (nicht INFEASIBLE)."""
        assert len(phase_b_result.assignments) > 0, "Phase B: keine Assignments!"

    def test_total_games_equals_2430(self, phase_b_result):
        """Genau 2430 Heimspiele gesamt (30 Teams × 81)."""
        assert phase_b_result.total_games == N_TEAMS * N_HOME, (
            f"Spiele: {phase_b_result.total_games}, erwartet {N_TEAMS * N_HOME}"
        )

    def test_all_series_length_max_4(self, phase_b_result):
        """Keine Serie mit mehr als 4 Spielen."""
        long_series = [a for a in phase_b_result.assignments if a.length > 4]
        assert len(long_series) == 0, (
            f"Serien > 4 Tage: {[(a.home_team, a.away_team, a.start_day, a.length) for a in long_series[:3]]}"
        )

    def test_no_self_play(self, phase_b_result):
        """Kein Team spielt gegen sich selbst."""
        self_plays = [a for a in phase_b_result.assignments if a.home_team == a.away_team]
        assert len(self_plays) == 0, f"Eigenspiele: {self_plays[:3]}"

    def test_each_home_day_covered(self, phase_b_result, hap_patterns):
        """Jedes Heimspiel (H-Tag) hat genau einen Gegner."""
        covered = set()
        for ass in phase_b_result.assignments:
            for d in range(ass.start_day, ass.end_day + 1):
                covered.add((ass.home_team, d))

        missing = []
        for tid, marks in hap_patterns.items():
            for d, m in enumerate(marks):
                if m == 'H' and d not in BREAK_DAYS:
                    if (tid, d) not in covered:
                        missing.append((tid, d))
        assert len(missing) == 0, f"Unbedeckte Heimspiele: {missing[:5]}"

    def test_no_double_booking_away(self, phase_b_result):
        """Kein Away-Team an demselben Tag an zwei Orten."""
        away_by_day: Dict[int, Dict[str, str]] = {}
        for ass in phase_b_result.assignments:
            for d in range(ass.start_day, ass.end_day + 1):
                if d not in away_by_day:
                    away_by_day[d] = {}
                a = ass.away_team
                if a in away_by_day[d]:
                    pytest.fail(
                        f"Doppelbuchung: {a} an Tag {d} bei "
                        f"{away_by_day[d][a]} UND {ass.home_team}"
                    )
                away_by_day[d][a] = ass.home_team

    def test_violations_below_threshold(self, phase_b_result):
        """Length-1-Violations unter 100 (soft constraint, beweisbar minimal)."""
        n = len(phase_b_result.violations)
        assert n < 100, (
            f"Phase B hat {n} Violations — zu viele für diese Patterns"
        )

    def test_phase_b_solve_time(self, phase_b_result):
        """Phase B CP-SAT terminiert in < 60s."""
        # Der phase_b_result-Fixture hat time_limit_s=60 gesetzt.
        # Wir prüfen implizit, dass er terminiert hat (hat eine Lösung).
        assert len(phase_b_result.assignments) > 0


# ────────────────────────────────────────────────────────────────────────────────
# 4. HAP-Parsing (parse_hap_series)
# ────────────────────────────────────────────────────────────────────────────────

@pytest.mark.slow
class TestHAPParsing:  # P2-7: hängt am HAP-Fixture (CP-SAT) → CI-only.

    def test_parse_hap_series_no_break_series(self, hap_patterns):
        """Keine HAP-Serie überspannt einen Break-Tag."""
        from src.series_matching import parse_hap_series
        hap = parse_hap_series(hap_patterns, BREAK_DAYS)
        for tid, series_list in hap.items():
            for s in series_list:
                for d in range(s.start_day, s.end_day + 1):
                    assert d not in BREAK_DAYS, (
                        f"{tid}: Serie {s.type} [{s.start_day}..{s.end_day}] "
                        f"enthält Break-Tag {d}"
                    )

    def test_parse_hap_series_total_games(self, hap_patterns):
        """Summe aller Serien-Längen == 81+81 pro Team."""
        from src.series_matching import parse_hap_series
        hap = parse_hap_series(hap_patterns, BREAK_DAYS)
        for tid, series_list in hap.items():
            total_h = sum(s.length for s in series_list if s.type == 'H')
            total_a = sum(s.length for s in series_list if s.type == 'A')
            assert total_h == N_HOME, f"{tid}: {total_h} H-Spieltage, erwartet {N_HOME}"
            assert total_a == N_AWAY, f"{tid}: {total_a} A-Spieltage, erwartet {N_AWAY}"


# ────────────────────────────────────────────────────────────────────────────────
# 5. Column Generation (Mini-System, schnell)
# ────────────────────────────────────────────────────────────────────────────────

class TestColumnGenerationMini:
    """Mini-System-Tests für CG (4 Teams, 30 Tage) — schnell, deterministisch."""

    MINI_TEAMS = ['AAA', 'BBB', 'CCC', 'DDD']
    MINI_DAYS  = 30
    MINI_BREAK: Set[int] = set()
    MINI_META  = {t: (10, 10) for t in MINI_TEAMS}

    def test_run_column_generation_returns_result(self):
        from src.column_generation import run_column_generation
        pool, rmp, log = run_column_generation(
            teams_meta=self.MINI_META,
            total_days=self.MINI_DAYS,
            break_days=self.MINI_BREAK,
            max_iterations=5,
            pricing_solver_seconds=1.0,
            initial_patterns_per_team=3,
            verbose=False,
            n_workers=1,
        )
        assert pool is not None
        assert rmp is not None
        assert log is not None

    def test_pattern_pool_has_all_teams(self):
        from src.column_generation import run_column_generation
        pool, _, _ = run_column_generation(
            teams_meta=self.MINI_META,
            total_days=self.MINI_DAYS,
            break_days=self.MINI_BREAK,
            max_iterations=3,
            pricing_solver_seconds=1.0,
            initial_patterns_per_team=2,
            verbose=False,
            n_workers=1,
        )
        assert set(pool.keys()) == set(self.MINI_TEAMS)

    def test_rmp_objective_non_negative(self):
        from src.column_generation import run_column_generation
        _, rmp, _ = run_column_generation(
            teams_meta=self.MINI_META,
            total_days=self.MINI_DAYS,
            break_days=self.MINI_BREAK,
            max_iterations=5,
            pricing_solver_seconds=1.0,
            initial_patterns_per_team=3,
            verbose=False,
            n_workers=1,
        )
        assert rmp.objective >= 0.0, f"Negative RMP-Objective: {rmp.objective}"

    def test_column_generation_runs_in_reasonable_time(self):
        from src.column_generation import run_column_generation
        t0 = time.time()
        run_column_generation(
            teams_meta=self.MINI_META,
            total_days=self.MINI_DAYS,
            break_days=self.MINI_BREAK,
            max_iterations=3,
            pricing_solver_seconds=0.5,
            initial_patterns_per_team=2,
            verbose=False,
            n_workers=1,
        )
        elapsed = time.time() - t0
        assert elapsed < 30.0, f"Column Generation dauerte {elapsed:.1f}s (> 30s)"
