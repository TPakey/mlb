"""Tests für Sprint 3 — Saison-Phasen (zeitfenster-basierte Gewichtung).

Schnelle, reine Tests des Phasen-Modells. Die Optimizer-Integration
(optimize_pareto mit phase_plan) ist als slow-Test markiert.
"""
from __future__ import annotations

from datetime import date

import pytest

from src.phases import PHASE_KEYS, PhasePlan, SchedulePhase


def test_phase_covers_and_mult():
    p = SchedulePhase("start", date(2026, 3, 26), date(2026, 4, 9),
                      {"tv": 3.0, "revenue": 2.0})
    assert p.covers(date(2026, 3, 26))      # Rand inklusiv
    assert p.covers(date(2026, 4, 9))
    assert not p.covers(date(2026, 4, 10))
    assert p.mult_for("tv") == 3.0
    assert p.mult_for("friction") == 1.0    # nicht gesetzt -> neutral


def test_plan_multiplier_default_one():
    plan = PhasePlan([SchedulePhase("s", date(2026, 4, 1), date(2026, 4, 5), {"tv": 5.0})])
    assert plan.multiplier(date(2026, 7, 1), "tv") == 1.0   # ausserhalb
    assert plan.multiplier(date(2026, 4, 3), "tv") == 5.0   # innerhalb
    assert plan.multiplier(date(2026, 4, 3), "revenue") == 1.0


def test_plan_overlapping_phases_multiply():
    plan = PhasePlan([
        SchedulePhase("a", date(2026, 4, 1), date(2026, 4, 10), {"tv": 2.0}),
        SchedulePhase("b", date(2026, 4, 5), date(2026, 4, 15), {"tv": 3.0}),
    ])
    # Überlappung am 7.4. → 2.0 * 3.0
    assert plan.multiplier(date(2026, 4, 7), "tv") == 6.0
    # Nur a am 2.4.
    assert plan.multiplier(date(2026, 4, 2), "tv") == 2.0


def test_empty_plan():
    plan = PhasePlan()
    assert plan.is_empty()
    assert plan.multiplier(date(2026, 5, 1), "tv") == 1.0


def test_roundtrip_dict():
    plan = PhasePlan([
        SchedulePhase("start", date(2026, 3, 26), date(2026, 4, 9), {"tv": 3.0, "revenue": 2.0}),
        SchedulePhase("end", date(2026, 9, 14), date(2026, 9, 27), {"tv": 4.0}),
    ])
    d = plan.to_dict()
    plan2 = PhasePlan.from_dict(d)
    assert len(plan2.phases) == 2
    assert plan2.multiplier(date(2026, 4, 1), "tv") == 3.0
    assert plan2.multiplier(date(2026, 9, 20), "tv") == 4.0


def test_unknown_dimension_rejected():
    with pytest.raises(ValueError):
        PhasePlan.from_dict({"phases": [
            {"name": "x", "start": "2026-04-01", "end": "2026-04-05",
             "multipliers": {"travel": 2.0}}  # travel nicht in V1-PHASE_KEYS
        ]})


def test_phase_keys_are_per_game_objectives():
    assert set(PHASE_KEYS) == {"revenue", "tv", "friction"}


@pytest.mark.slow
def test_phase_plan_shifts_window_tv_up():
    """Integrationstest: ein TV-Boost im Saisonstart-Fenster hebt den TV-Wert
    dort gegenüber einem phasenlosen Lauf (gleicher Seed)."""
    from datetime import timedelta

    from src.data_loader import load_teams
    from src.datasources import LocalFileAdapter
    from src.generator import GeneratorConfig
    from src.generator_optimizer import OptimizerConfig, optimize_pareto, optimize_travel
    from src.profiles import PARETO_PROFILES
    from src.season import Season
    from src.tv_slots import TvSlotConfig, compute_tv_slot_score

    teams = load_teams()
    real = LocalFileAdapter(base_dir="data").fetch_season_schedule(2024)
    ss, se = real.season_start, real.season_end
    cfg = GeneratorConfig(season=2024, season_start=ss, season_end=se, all_star_break=None,
                          max_solver_time_seconds=60, random_seed=42,
                          enforce_fatigue_constraints=True)
    base, _ = optimize_travel(real, teams, cfg,
                              OptimizerConfig(iterations=300_000, move_mix_geo=0.35,
                                              seed=42, fatigue_lambda=1_000_000.0))
    tvc = TvSlotConfig.load()
    win = (ss, ss + timedelta(days=14))

    def window_tv(season):
        sub = [g for g in season.games if win[0] <= g.date <= win[1]]
        return compute_tv_slot_score(
            Season(season=season.season, games=sub, season_start=ss, season_end=se), tvc
        ).total_score

    prof = PARETO_PROFILES["tv_optimized"]
    s_no, b_no, _ = optimize_pareto(base, teams, cfg, prof, iterations=40000, seed=7)
    plan = PhasePlan([SchedulePhase("start", win[0], win[1], {"tv": 6.0})])
    s_ph, b_ph, _ = optimize_pareto(base, teams, cfg, prof, iterations=40000, seed=7,
                                    phase_plan=plan)
    # Fenster-TV mit Phase >= ohne Phase (Boost wirkt richtungsweisend).
    assert window_tv(s_ph) >= window_tv(s_no)
    # Keine neuen CBA-Verletzungen.
    assert b_ph.constraint_violations == 0
