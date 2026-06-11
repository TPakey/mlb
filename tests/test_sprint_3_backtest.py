"""Tests für Sprint 3 / Track B — Backtest-Harness (tools/backtest.py).

Schnelle Tests: bewerten den realen Plan (B1) und prüfen die Delta-/Report-Logik.
Der langsame Generierungspfad (B2) wird hier NICHT ausgeführt (CP-SAT) — er ist
über tools/backtest.py manuell / in CI abgedeckt. Diese Tests bleiben < 1 s.
"""
from __future__ import annotations

import pytest

from tools import backtest as bt


# ---------------------------------------------------------------
# B1 — reale Baseline
# ---------------------------------------------------------------

def test_load_real_baseline_2024():
    ev = bt.load_real_baseline(2024)
    assert ev.n_games == 2432
    assert ev.n_doubleheaders > 0
    # Reale Saison hält die CBA-Regeln ein (von Hand geplant).
    assert ev.bundle.constraint_violations == 0
    assert ev.bundle.max_away_streak <= 13
    # Plausible Liga-Reisedistanz (1.5–2.0 Mio km Korridor).
    assert 1_400_000 < ev.bundle.travel_km < 2_000_000
    # Alle 30 Teams im Travel-Report.
    assert len(ev.travel.by_team) == 30


def test_baseline_per_team_travel_sorted_desc():
    ev = bt.load_real_baseline(2024)
    result = bt.BacktestResult(season_year=2024, baseline=ev, ours=None)
    rows = bt.per_team_travel_rows(result)
    kms = [r["baseline_km"] for r in rows]
    assert kms == sorted(kms, reverse=True)
    assert len(rows) == 30


# ---------------------------------------------------------------
# Delta-Logik (ohne Generierung — synthetische "ours")
# ---------------------------------------------------------------

def _fake_eval(label, base_eval, **overrides):
    """Klont eine PlanEvaluation mit überschriebenen Bundle-Feldern."""
    from dataclasses import replace
    b = base_eval.bundle
    new_bundle = replace(b, **overrides)
    return bt.PlanEvaluation(
        label=label, season=base_eval.season, bundle=new_bundle,
        travel=base_eval.travel, n_games=base_eval.n_games,
        n_doubleheaders=base_eval.n_doubleheaders,
        season_start=base_eval.season_start, season_end=base_eval.season_end,
        solve_seconds=1.0, status="OPTIMAL", seed=42,
    )


def test_verdict_direction():
    # travel_km: niedriger = besser
    assert bt._verdict("travel_km", False, 100.0, 200.0) == "besser"
    assert bt._verdict("travel_km", False, 300.0, 200.0) == "schlechter"
    # revenue_usd: höher = besser
    assert bt._verdict("revenue_usd", True, 300.0, 200.0) == "besser"
    assert bt._verdict("revenue_usd", True, 100.0, 200.0) == "schlechter"
    assert bt._verdict("travel_km", False, 200.0, 200.0) == "gleich"


def test_pct_delta_zero_base():
    assert bt._pct_delta(5.0, 0.0) is None
    assert bt._pct_delta(150.0, 100.0) == pytest.approx(50.0)


def test_dimension_rows_have_all_eight():
    ev = bt.load_real_baseline(2024)
    better = _fake_eval("ours", ev, travel_km=ev.bundle.travel_km - 50_000)
    result = bt.BacktestResult(season_year=2024, baseline=ev, ours=better)
    rows = bt.compute_dimension_rows(result)
    assert len(rows) == 8
    travel_row = next(r for r in rows if r["key"] == "travel_km")
    assert travel_row["verdict"] == "besser"
    assert travel_row["delta"] == pytest.approx(-50_000)


# ---------------------------------------------------------------
# Report-Rendering (smoke)
# ---------------------------------------------------------------

def test_render_markdown_and_html_smoke():
    ev = bt.load_real_baseline(2024)
    ours = _fake_eval("ours", ev, travel_km=ev.bundle.travel_km - 10_000,
                      constraint_violations=2)
    result = bt.BacktestResult(season_year=2024, baseline=ev, ours=ours)
    md = bt.render_markdown(result)
    html = bt.render_html(result)
    assert "Backtest" in md and "Pro-Team" in md
    assert "<table" in html and "Ehrlichkeits" in html
    # JSON serialisierbar
    import json
    js = json.dumps(bt.render_json(result), default=str)
    assert "baseline" in js and "dimensions" in js


def test_detect_all_star_break_2024():
    ev = bt.load_real_baseline(2024)
    asb = bt._detect_all_star_break(ev.season)
    assert asb is not None
    start, end = asb
    # ASB liegt Mitte Juli.
    assert start.month == 7 and 10 <= start.day <= 20
    assert end >= start


# ---------------------------------------------------------------
# Warm-Start — schlaegt den realen Plan (langsam: SA-Lauf)
# ---------------------------------------------------------------

@pytest.mark.slow
def test_warm_start_beats_real_and_preserves_games():
    """Warm-Start vom realen Plan: schlaegt ihn auf Reise, bleibt CBA-konform,
    verliert KEINE Spiele (Doubleheader erhalten)."""
    real = bt.load_real_baseline(2024)
    improved = bt.improve_real_plan(2024, seed=42, iterations=1_000_000)
    # Keine Spiele verloren (Doubleheader-Roundtrip korrekt).
    assert improved.n_games == real.n_games == 2432
    # Reise echt besser als der reale Plan.
    assert improved.bundle.travel_km < real.bundle.travel_km
    # CBA bleibt eingehalten (nicht schlechter als real = 0).
    assert improved.bundle.constraint_violations == 0
    assert improved.bundle.max_away_streak <= 13


@pytest.mark.slow
def test_warm_start_deterministic():
    a = bt.improve_real_plan(2024, seed=42, iterations=500_000)
    b = bt.improve_real_plan(2024, seed=42, iterations=500_000)
    assert a.bundle.travel_km == b.bundle.travel_km
