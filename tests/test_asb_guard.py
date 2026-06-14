"""ASB-Fehlbedienungs-Guard (Finalisierung Punkt 3).

Falscher/fehlender All-Star-Break ließ den V(C)(13)-Penalty gegen das falsche
Modell optimieren und erzeugte still neue Verstöße (~29 auf dem 2026-Original
bei ASB=None) — ein scheinbar besserer Plan (−2,31 % statt −1,7 %), weil
Verstöße km sparen, gefangen erst vom Gate. Der Guard kippt das früh.
"""
from __future__ import annotations

import pytest

from src.data_loader import load_teams
from src.generator import GeneratorConfig
from src.generator_optimizer import (
    OptimizerConfig, optimize_travel, production_optimizer_config,
)
from src.original_schedule import load_original_schedule
from src.season import detect_all_star_break


def test_default_config_has_guard_off():
    """Default-Pfad unverändert (bit-identisch): Guard aus."""
    assert OptimizerConfig().require_all_star_break is False
    assert OptimizerConfig().sched13_lambda == 0.0


def test_production_config_enables_guard():
    assert production_optimizer_config().require_all_star_break is True


def _cfg(orig, asb, iters=20_000):
    return GeneratorConfig(
        season=2026, season_start=orig.season_start, season_end=orig.season_end,
        all_star_break=asb, max_solver_time_seconds=60, num_search_workers=1,
        random_seed=42, enforce_fatigue_constraints=True,
        travel_optimizer_iterations=iters)


def test_guard_trips_on_missing_asb():
    """Produktions-Config + ASB=None → früher ValueError (nicht erst das Gate)."""
    orig, _ = load_original_schedule(2026)
    teams = load_teams()
    oc = production_optimizer_config(iterations=20_000, seed=42)
    with pytest.raises(ValueError, match="ASB-Guard"):
        optimize_travel(orig, teams, _cfg(orig, None), oc)


def test_guard_allows_correct_asb():
    """Mit korrektem ASB läuft der Produktionspfad normal durch."""
    orig, _ = load_original_schedule(2026)
    teams = load_teams()
    oc = production_optimizer_config(iterations=20_000, seed=42)
    improved, _log = optimize_travel(orig, teams,
                                     _cfg(orig, detect_all_star_break(orig)), oc)
    assert improved is not None
    assert len(improved.games) == len(orig.games)
