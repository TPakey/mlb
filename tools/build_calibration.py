"""Kalibrier-Harness fuer die Vorab-Schaetzungen des Regler-Dashboards (Sprint 3).

Zweck: Das Dashboard (dashboard/phase_tuner.html) soll die Wirkung eines Reglers schon
VOR dem teuren Optimizer-Lauf realistisch anzeigen. Dazu vermessen wir den Optimizer an
wenigen Stuetzstellen und speichern eine kompakte Antwortkurve, die das Dashboard live
interpoliert.

Methodik (recherchiert, MLB-auditierbar):
- Surrogat = **gemessenes Raster + monotone Interpolation** (kein GP/RBF-Black-Box).
  Begruendung: niedrige Dimension, glatte/monotone Antwort, wenige Stuetzstellen,
  Auditierbarkeit. Die Literatur (Kriging vs. RBF vs. Polynom) zeigt keinen universellen
  Sieger; fuer diesen Fall ist treue Interpolation echter Messpunkte am ehrlichsten.
- **Energie-Struktur ausnutzen:** Das TV-/Revenue-Gewicht eines Fenster-Spiels ist im
  Energiefunktional w_dim x phase_mult. Wir kalibrieren die Fenster-Wirkung daher als 1D-
  Kurve ueber den **effektiven Faktor = phase_mult** (bei Referenz-Gewicht) und testen die
  Produkt-Kollaps-Hypothese (variiere w_dim separat). Das Dashboard skaliert linear mit
  (aktuelles_Gewicht / Referenz-Gewicht).

Ausgabe: data/phase_calibration.json. Mehrfach aufrufbar (--dim tv|revenue), Ergebnisse
werden gemerged.

    python -m tools.build_calibration --dim tv --season 2024
    python -m tools.build_calibration --dim revenue --season 2024
"""

# REVIEW-FIX RUNDE 2 (Punkt 0, Aufrufer-Audit 2026-06-10): Dieses Tool ist ein
# FORSCHUNGS-INSTRUMENT (Kalibrierung/Diagnose), KEIN Plan-Output-Pfad. Es
# erzeugt keine auslieferbaren Plaene; Plan-Outputs laufen ausschliesslich
# ueber die gate-gesicherten Pfade (backtest/main/api/pareto/whatif/disruption).

from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path

from src.data_loader import load_teams
from src.datasources import LocalFileAdapter
from src.generator import GeneratorConfig
from src.generator_optimizer import OptimizerConfig, optimize_pareto, optimize_travel
from src.phases import PhasePlan, SchedulePhase
from src.profiles import ParetoProfile
from src.revenue import RevenueModel, build_division_rivals, expected_revenue_raw
from src.season import Season, detect_all_star_break
from src.tv_slots import TvSlotConfig, compute_tv_slot_score

OUT = Path("data/phase_calibration.json")

# Messung (2026-06-02): Der wirksame Hebel ist der **Phasen-Multiplikator** (er
# KONZENTRIERT TV/Revenue ins Fenster), nicht das globale Gewicht (das hebt die
# Dimension ueberall). Wir kalibrieren daher den Multiplikator-Sweep MIT Phasenplan
# bei festem, hinreichend starkem Gewicht (sonst greift der Hebel nicht), bei 40k
# Iterationen (wie der "Rechnen"-Default). Das Dashboard interpoliert phase_mult →
# Fenster-Uplift und skaliert mit dem globalen Gewichts-Regler (Aktivierungs-Faktor).
STRONG_WEIGHT = {"tv": -3000.0, "revenue": -8.0e-6}
PHASE_MULTS = [1.0, 2.0, 4.0, 8.0]
CAL_ITERS = 80_000
WIN_DAYS = 14


def _window(season, ss, se, start, end, tv_cfg, rev_model, rivals):
    sub = [g for g in season.games if start <= g.date <= end]
    s2 = Season(season=season.season, games=sub, season_start=ss, season_end=se)
    tv = compute_tv_slot_score(s2, tv_cfg).total_score
    rev = sum(expected_revenue_raw(g.date, g.home, g.away, 0, rev_model, rivals) for g in sub)
    return tv, rev, len(sub)


def calibrate(dim: str, season_year: int, seed: int) -> dict:
    teams = load_teams()
    real = LocalFileAdapter(base_dir="data").fetch_season_schedule(season_year)
    ss, se = real.season_start, real.season_end
    win = (ss, ss + timedelta(days=WIN_DAYS))
    cfg = GeneratorConfig(season=season_year, season_start=ss, season_end=se,
                          all_star_break=detect_all_star_break(real),
                          max_solver_time_seconds=60, random_seed=seed,
                          enforce_fatigue_constraints=True)
    tv_cfg, rev_model = TvSlotConfig.load(), build_division_rivals(teams)
    rev_model_obj = RevenueModel.load()
    metric_idx = 0 if dim == "tv" else 1

    def wmetric(season):
        tv, rev, n = _window(season, ss, se, win[0], win[1], tv_cfg, rev_model_obj, rev_model)
        return (tv, rev, n)[metric_idx], n

    base, _ = optimize_travel(real, teams, cfg, OptimizerConfig(
        iterations=300_000, move_mix_geo=0.35, seed=seed, fatigue_lambda=1_000_000.0))
    real_win, n_win = wmetric(real)

    wkey = "w_" + dim
    strong_w = STRONG_WEIGHT[dim]
    prof = ParetoProfile.free(name="cal", **{wkey: strong_w})
    # Multiplikator-Sweep MIT Phasenplan (Konzentration ins Fenster).
    curve = []
    for m in PHASE_MULTS:
        pp = None if m == 1.0 else PhasePlan([SchedulePhase("w", win[0], win[1], {dim: m})])
        opt, b, _ = optimize_pareto(base, teams, cfg, prof, iterations=CAL_ITERS,
                                    seed=seed, phase_plan=pp)
        wv, _ = wmetric(opt)
        curve.append({"mult": m, "window_metric": round(wv, 2),
                      "uplift_ratio": round(wv / real_win, 4) if real_win else None,
                      "global_travel_km": round(b.travel_km),
                      "violations": b.constraint_violations})

    return {
        "dimension": dim,
        "season_year": season_year,
        "iterations": CAL_ITERS,
        "strong_weight": strong_w,
        "window_days": WIN_DAYS,
        "real_window_metric": round(real_win, 2),
        "n_window_games": n_win,
        "curve": curve,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Kalibrier-Raster fuer die Dashboard-Schaetzungen")
    p.add_argument("--dim", required=True, choices=["tv", "revenue"])
    p.add_argument("--season", type=int, default=2024)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    data = {}
    if OUT.exists():
        data = json.loads(OUT.read_text(encoding="utf-8"))
    data.setdefault("dimensions", {})
    data["dimensions"][args.dim] = calibrate(args.dim, args.season, args.seed)
    data["_meta"] = {"method": "measured-grid + monotone interpolation",
                     "note": "Vorab-Schaetzungen; echte Werte via tools.tune_run / /tune/evaluate."}
    OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"calibration[{args.dim}] -> {OUT}")
    c = data["dimensions"][args.dim]
    print(f"  real_window={c['real_window_metric']}  (Multiplikator-Sweep, Phasenplan):")
    for pt in c["curve"]:
        print(f"    mult={pt['mult']:>4} -> uplift={pt['uplift_ratio']:>6}  "
              f"km={pt['global_travel_km']:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
