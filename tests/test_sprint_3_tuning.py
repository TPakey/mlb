"""Tests für Sprint 3 — Tuner-Feedback-Schleife (tools/tuning.evaluate_tuning).

Der eigentliche Optimizer-Lauf ist langsam (slow). Hier ein Struktur-/Wirkungstest.
"""
from __future__ import annotations

import pytest

BALANCED_W = {
    "w_travel": 1.0, "w_revenue": -5e-7, "w_fatigue": 20.0, "w_away_streak": 5000.0,
    "w_off_day": 20_000_000.0, "w_tv": -200.0, "w_friction": 500.0,
    "violations_penalty": 1e9,
}


@pytest.mark.slow
def test_evaluate_tuning_structure_and_compliance():
    from tools.tuning import evaluate_tuning
    plan = {"phases": [
        {"name": "Start", "start": "2024-03-20", "end": "2024-04-07",
         "multipliers": {"tv": 4.0, "revenue": 2.0}},
    ]}
    res = evaluate_tuning(BALANCED_W, plan, season_year=2024, seed=42,
                          warm_iterations=300_000, pareto_iterations=8_000)
    # Struktur
    assert set(res["dimensions"]) >= {"travel_km", "tv_slot_score", "constraint_violations"}
    assert len(res["windows"]) == 1
    w = res["windows"][0]
    assert "optimized" in w and "real" in w
    # Warm-Start schlägt den realen Plan auf Reise und bleibt CBA-konform.
    assert res["summary"]["travel_vs_real_pct"] < 0
    assert res["summary"]["cba_compliant"] is True


@pytest.mark.slow
def test_tv_phase_concentrates_window():
    """Ein TV-Boost im Fenster hebt dort den TV-Score gegenüber dem realen Plan."""
    from tools.tuning import evaluate_tuning
    tv_heavy = dict(BALANCED_W, w_tv=-1500.0)
    plan = {"phases": [
        {"name": "Start", "start": "2024-03-20", "end": "2024-04-07",
         "multipliers": {"tv": 6.0}},
    ]}
    res = evaluate_tuning(tv_heavy, plan, season_year=2024, seed=42,
                          warm_iterations=300_000, pareto_iterations=12_000)
    w = res["windows"][0]
    assert w["optimized"]["tv_slot_score"] >= w["real"]["tv_slot_score"]
