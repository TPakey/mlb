"""End-to-end Smoke-Test: lädt alle Module, optimiert, validiert.

Lauf mit:
    python -m tests.test_end_to_end
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.legacy import tradeoff_profiles as P
from src.legacy.constraints import validate
from src.data_loader import load_soft_factors, load_teams, teams_by_id
from src.distance import distance_matrix
from src.legacy.metrics import compute_metrics
from src.legacy.optimizer import OptimizationConfig, optimize
from src.legacy.schedule_generator import generate_baseline_schedule
from src.legacy.scoring import compute_scores
from src.legacy.ai_explainer import narrate


def assert_(cond: bool, msg: str) -> None:
    if not cond:
        print(f"  FAIL: {msg}")
        raise SystemExit(1)
    print(f"  OK:   {msg}")


def main() -> int:
    print("=== End-to-end Smoke-Test ===\n")

    print("[1] Daten laden")
    teams = load_teams()
    sf = load_soft_factors()
    tbi = teams_by_id(teams)
    assert_(len(teams) == 30, "30 Teams geladen")
    assert_(len(sf["events"]) > 10, "Soft-Factor-Events vorhanden")

    print("\n[2] Distanzmatrix berechnen")
    km_map, leg_map = distance_matrix(teams)
    assert_(len(km_map) == 30 * 30, "Distanzmatrix 30x30")
    assert_(km_map[("LAD", "BOS")] > 4000, "LA→Boston > 4000 km (Sanity)")
    assert_(km_map[("LAD", "LAD")] == 0, "Selbst-Distanz = 0")

    print("\n[3] Baseline-Schedule generieren")
    baseline = generate_baseline_schedule(teams, seed=42)
    assert_(len(baseline.series) == 27 * 15, "27 Slots × 15 Serien = 405 Serien")

    print("\n[4] Hard-Constraint-Validierung")
    rep = validate(baseline, teams, tbi)
    assert_(rep.is_valid, "Baseline-Plan ist hard-constraint-valid")

    print("\n[5] Initial-Scores berechnen")
    bundle = compute_scores(baseline, teams, tbi, leg_map, sf)
    assert_(bundle.travel.score > 0, "Travel-Score > 0")
    assert_(bundle.fairness.score > 0, "Fairness-Score > 0")
    assert_("total_km" in bundle.travel.components, "Travel hat Detail-Komponenten")

    print("\n[6] Optimierung (kurz, 300 Iterationen)")
    profile = P.get("balanced")
    cfg = OptimizationConfig(iterations=300, seed=7, log_every=50)
    result = optimize(baseline, teams, tbi, leg_map, sf, profile, cfg)
    assert_(result.final_cost <= result.initial_cost, "Kosten sind nicht gestiegen")
    assert_(result.accepted_moves > 0, "Mindestens ein Move akzeptiert")
    print(f"        Δkm:  {result.initial_bundle.travel.components['total_km']:.0f} → "
          f"{result.final_bundle.travel.components['total_km']:.0f}")
    print(f"        Δcost:{result.initial_cost:.0f} → {result.final_cost:.0f}")

    print("\n[7] Post-Hard-Constraints des optimierten Plans")
    rep2 = validate(result.schedule, teams, tbi)
    assert_(rep2.is_valid, "Optimierter Plan ist hard-constraint-valid")

    print("\n[8] KPIs berechnen")
    m_base = compute_metrics(baseline, teams, leg_map)
    m_opt = compute_metrics(result.schedule, teams, leg_map)
    assert_(m_opt.total_km <= m_base.total_km, "Optimierte km ≤ Baseline km")
    print(f"        Baseline:  {m_base.total_km:,.0f} km")
    print(f"        Optimiert: {m_opt.total_km:,.0f} km")
    print(f"        Δ:         {m_base.total_km - m_opt.total_km:,.0f} km gespart")

    print("\n[9] Narrative generieren")
    n = narrate(result, teams)
    assert_(len(n.headline) > 0, "Headline nicht leer")
    assert_(len(n.key_tradeoffs) > 0, "Mindestens ein Tradeoff dokumentiert")
    assert_(len(n.recommendation) > 0, "Empfehlung vorhanden")

    print("\n[10] Profil-Vielfalt")
    profile_names = list(P.PROFILES.keys())
    assert_(len(profile_names) == 6, "6 Tradeoff-Profile registriert")
    assert_("balanced" in profile_names, "balanced existiert")
    assert_("player_health" in profile_names, "player_health existiert")
    assert_("revenue_max" in profile_names, "revenue_max existiert")

    print("\n=== Alle Tests bestanden ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
