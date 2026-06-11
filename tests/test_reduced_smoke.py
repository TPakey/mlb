"""Schnelle Smoke-Tests auf reduzierter Instanz (P2-7).

Deckt den Warm-Start-/optimize_travel-Pfad in < 5 s ab, ohne den vollen
30-Team-CP-SAT-Solve (der als `@slow`/CI-only markiert ist). Läuft in der
Sandbox problemlos.
"""
from __future__ import annotations

import pytest

from src.datasources import LocalFileAdapter
from src.data_loader import load_teams, teams_by_id
from src.generator import GeneratorConfig
from src.generator_optimizer import OptimizerConfig, optimize_travel
from src.reduced_instance import build_reduced_season, AL_EAST
from src.season import detect_all_star_break
from src.player_fatigue import all_teams_pass_fatigue_constraints


@pytest.fixture(scope="module")
def reduced(data_dir):
    full = LocalFileAdapter(base_dir=str(data_dir)).fetch_season_schedule(2024)
    return build_reduced_season(full, AL_EAST)


def _cfg(reduced):
    return GeneratorConfig(
        season=2024, season_start=reduced.season_start,
        season_end=reduced.season_end,
        all_star_break=detect_all_star_break(reduced),
        num_search_workers=1, random_seed=42, enforce_fatigue_constraints=True,
    )


def test_reduced_instance_is_consistent(reduced):
    assert len(reduced.games) > 0
    teams = {g.home for g in reduced.games} | {g.away for g in reduced.games}
    assert teams <= set(AL_EAST)                       # nur die Teilmenge
    # jedes Spiel ist intra-Cluster
    for g in reduced.games:
        assert g.home in AL_EAST and g.away in AL_EAST


def test_warm_start_path_runs_fast_and_deterministic(reduced):
    teams = load_teams()
    cfg = _cfg(reduced)
    oc = OptimizerConfig(iterations=8000, move_mix_geo=0.35, seed=42,
                         fatigue_lambda=1_000_000.0)
    s1, l1 = optimize_travel(reduced, teams, cfg, oc)
    s2, l2 = optimize_travel(reduced, teams, cfg, oc)
    assert l1.final_km == l2.final_km                  # deterministisch
    assert l1.final_km <= l1.initial_km                # verbessert (oder gleich)
    # Spielmenge erhalten
    assert len(s1.games) == len(reduced.games)


def test_reduced_terms_run(reduced):
    # Feasibility/Holiday/DH-Pfade laufen auch auf der reduzierten Instanz.
    teams = load_teams()
    cfg = _cfg(reduced)
    oc = OptimizerConfig(iterations=6000, move_mix_geo=0.35, seed=42,
                         fatigue_lambda=1_000_000.0, feas_lambda=50_000.0,
                         holiday_lambda=5_000.0, enable_dh_compression=True)
    s, log = optimize_travel(reduced, teams, cfg, oc)
    assert len(s.games) == len(reduced.games)
    # AC-Checks sind auf der Teilmenge prüfbar (kein Crash, valides Ergebnis).
    ok, _ = all_teams_pass_fatigue_constraints(s, list(AL_EAST))
    assert isinstance(ok, bool)
