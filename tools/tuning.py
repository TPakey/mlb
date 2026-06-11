"""Tuner-Auswertung — eine Scheduler-Konfiguration tatsaechlich rechnen (Sprint 3).

Schliesst die Feedback-Schleife des Regler-Dashboards (dashboard/phase_tuner.html):
Nimmt die exportierte Konfiguration (Profil-Gewichte + Phasenplan), startet vom
realen Plan (Warm-Start), optimiert mit genau diesen Prioritaeten und gibt die
*tatsaechlichen* Zahlen zurueck — global vs. realer Plan plus pro-Fenster-Kennzahlen.

Gemeinsam genutzt von der CLI (tools/tune_run.py) und der REST-API (/tune/evaluate).
"""

# REVIEW-FIX RUNDE 2 (Punkt 0, Aufrufer-Audit 2026-06-10): Dieses Tool ist ein
# FORSCHUNGS-INSTRUMENT (Kalibrierung/Diagnose), KEIN Plan-Output-Pfad. Es
# erzeugt keine auslieferbaren Plaene; Plan-Outputs laufen ausschliesslich
# ueber die gate-gesicherten Pfade (backtest/main/api/pareto/whatif/disruption).

from __future__ import annotations

from typing import Dict, Optional

from src.data_loader import load_teams
from src.datasources import LocalFileAdapter
from src.generator import GeneratorConfig
from src.generator_optimizer import OptimizerConfig, optimize_pareto, optimize_travel
from src.pareto_types import compute_pareto_bundle
from src.phases import PhasePlan
from src.profiles import ParetoProfile
from src.revenue import RevenueModel, build_division_rivals, expected_revenue_raw
from src.season import Season, detect_all_star_break
from src.tv_slots import TvSlotConfig, compute_tv_slot_score


def _window_metrics(season: Season, start, end, tv_cfg, rev_model, rivals) -> Dict[str, float]:
    """TV-Score + Revenue der Spiele innerhalb eines Datumsfensters [start, end]."""
    sub = [g for g in season.games if start <= g.date <= end]
    if not sub:
        return {"games": 0, "tv_slot_score": 0.0, "revenue_usd": 0.0}
    sub_season = Season(season=season.season, games=sub,
                        season_start=season.season_start, season_end=season.season_end)
    tv = compute_tv_slot_score(sub_season, tv_cfg).total_score
    rev = sum(expected_revenue_raw(g.date, g.home, g.away, 0, rev_model, rivals) for g in sub)
    return {"games": len(sub), "tv_slot_score": round(tv, 1), "revenue_usd": round(rev)}


def evaluate_tuning(
    profile_weights: Dict[str, float],
    phase_plan_dict: Optional[dict] = None,
    season_year: int = 2024,
    seed: int = 42,
    warm_iterations: int = 1_000_000,
    pareto_iterations: int = 80_000,
) -> dict:
    """Rechnet eine Tuner-Konfiguration und liefert echte Kennzahlen.

    Args:
        profile_weights:  {w_travel, w_revenue, ...} aus dem Dashboard-Export.
        phase_plan_dict:  {"phases": [...]} aus dem Export (oder None).
        season_year:      Saison, deren realer Plan als Warm-Start dient.
        seed:             Deterministischer Seed.
        warm_iterations:  SA-Iterationen fuer den Warm-Start (Travel).
        pareto_iterations: SA-Iterationen fuer die gewichtete Pareto-Optimierung.

    Returns:
        dict mit real-Baseline, optimiertem Bundle, Deltas und Pro-Fenster-Kennzahlen.
    """
    teams = load_teams()
    real = LocalFileAdapter(base_dir="data").fetch_season_schedule(season_year)
    ss, se = real.season_start, real.season_end

    cfg = GeneratorConfig(
        season=season_year, season_start=ss, season_end=se,
        all_star_break=detect_all_star_break(real),
        max_solver_time_seconds=60, random_seed=seed,
        enforce_fatigue_constraints=True,
    )

    profile = ParetoProfile.free(name="tuner", description="Dashboard-Tuning",
                                 **profile_weights)
    phase_plan = PhasePlan.from_dict(phase_plan_dict) if phase_plan_dict else None

    # 1) Warm-Start: realen Plan reise-optimieren (CBA-konform, schlaegt real).
    base, _ = optimize_travel(real, teams, cfg, OptimizerConfig(
        iterations=warm_iterations, move_mix_geo=0.35, seed=seed,
        fatigue_lambda=1_000_000.0))
    # 2) Gewichtete Pareto-Optimierung mit den Scheduler-Prioritaeten + Phasen.
    opt, bundle, _ = optimize_pareto(base, teams, cfg, profile,
                                     iterations=pareto_iterations, seed=seed,
                                     phase_plan=phase_plan)

    real_bundle = compute_pareto_bundle(real, teams)

    tv_cfg = TvSlotConfig.load()
    rev_model = RevenueModel.load()
    rivals = build_division_rivals(teams)

    def _delta(key, higher_better):
        rv = float(getattr(real_bundle, key))
        ov = float(getattr(bundle, key))
        pct = (ov - rv) / abs(rv) * 100.0 if rv else None
        better = (ov > rv) if higher_better else (ov < rv)
        return {"real": rv, "ours": ov, "pct": (round(pct, 2) if pct is not None else None),
                "verdict": ("besser" if ov != rv and better else
                            ("gleich" if ov == rv else "schlechter"))}

    dims = {
        "travel_km": _delta("travel_km", False),
        "revenue_usd": _delta("revenue_usd", True),
        "fatigue_score": _delta("fatigue_score", False),
        "max_away_streak": _delta("max_away_streak", False),
        "tv_slot_score": _delta("tv_slot_score", True),
        "event_friction": _delta("event_friction", False),
        "constraint_violations": _delta("constraint_violations", False),
    }

    # Pro-Fenster-Kennzahlen je definierter Phase.
    windows = []
    if phase_plan is not None:
        for p in phase_plan.phases:
            windows.append({
                "name": p.name,
                "start": p.start.isoformat(),
                "end": p.end.isoformat(),
                "multipliers": dict(p.multipliers),
                "optimized": _window_metrics(opt, p.start, p.end, tv_cfg, rev_model, rivals),
                "real": _window_metrics(real, p.start, p.end, tv_cfg, rev_model, rivals),
            })

    return {
        "season_year": season_year,
        "seed": seed,
        "dimensions": dims,
        "windows": windows,
        "summary": {
            "travel_km": bundle.travel_km,
            "travel_vs_real_pct": dims["travel_km"]["pct"],
            "constraint_violations": bundle.constraint_violations,
            "cba_compliant": bundle.constraint_violations == 0,
        },
    }
