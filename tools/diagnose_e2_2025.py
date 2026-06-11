"""E2-Diagnose (Sprint 5.3): warum erreicht der Warm-Start 2025 weniger km-Einsparung
als 2024? Misst (a) reale Baseline-km, (b) erreichbaren Delta bei GLEICHER Iterations-
zahl, (c) strukturelle Unterschiede (Relokationen/Intl/Spielzahl-Streuung).
Reine Messung. Iterationszahl via ARGV[1] (Default 60000, sandbox-tauglich)."""

# REVIEW-FIX RUNDE 2 (Punkt 0, Aufrufer-Audit 2026-06-10): Dieses Tool ist ein
# FORSCHUNGS-INSTRUMENT (Kalibrierung/Diagnose), KEIN Plan-Output-Pfad. Es
# erzeugt keine auslieferbaren Plaene; Plan-Outputs laufen ausschliesslich
# ueber die gate-gesicherten Pfade (backtest/main/api/pareto/whatif/disruption).

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data_loader import load_teams
from src.datasources.local_file import LocalFileAdapter
from src.season import detect_all_star_break
from src.generator_optimizer import GeneratorConfig, OptimizerConfig, optimize_travel
from src.travel import compute_season_travel

ITERS = int(sys.argv[1]) if len(sys.argv) > 1 else 60_000


def structural(season, teams_by_id):
    # Heim-Venues je Team (Relokationen erzeugen abweichende venue-Namen)
    venues_per_home = {}
    intl = 0
    for g in season.games:
        venues_per_home.setdefault(g.home, set()).add(g.venue)
    # internationale/neutrale Spielorte
    NEUTRAL = ("Seoul", "London", "Tokyo", "Mexico", "Gocheok", "Sky Dome", "Estadio")
    intl = sum(1 for g in season.games
               if any(h.lower() in (g.venue or "").lower() for h in NEUTRAL))
    # Teams, deren Heimspiele NICHT im eigenen Stadion (Relokation)
    relocated = {}
    for home, vs in venues_per_home.items():
        std = teams_by_id[home].stadium if home in teams_by_id else None
        if std and not any(std.split()[0] in v for v in vs):
            relocated[home] = sorted(vs)
    counts = Counter()
    for g in season.games:
        counts[g.home] += 1
        counts[g.away] += 1
    return intl, relocated, (min(counts.values()), max(counts.values()))


def run_year(year, teams, tbi):
    real = LocalFileAdapter(base_dir=str(ROOT / "data")).fetch_season_schedule(year)
    real_km = compute_season_travel(real, teams).total_km
    cfg = GeneratorConfig(
        season=year, season_start=real.season_start, season_end=real.season_end,
        all_star_break=detect_all_star_break(real),
        num_search_workers=1, random_seed=42, enforce_fatigue_constraints=True,
        travel_optimizer_iterations=ITERS)
    oc = OptimizerConfig(iterations=ITERS, move_mix_geo=0.35, seed=42,
                         fatigue_lambda=1_000_000.0)
    improved, log = optimize_travel(real, teams, cfg, oc)
    opt_km = compute_season_travel(improved, teams).total_km
    intl, relocated, span = structural(real, tbi)
    delta = (opt_km - real_km) / real_km * 100
    print(f"\n===== {year} (Iter={ITERS}) =====")
    print(f"real km           : {real_km:,.0f}")
    print(f"optimiert km      : {opt_km:,.0f}  (Δ {delta:+.2f}%)")
    print(f"intl/neutral Spiele: {intl}")
    print(f"Spiele/Team-Spanne : {span}")
    print(f"relozierte Heim-Teams: {list(relocated)}")
    for t, vs in relocated.items():
        print(f"   {t}: {vs}")
    return real_km, opt_km, delta


if __name__ == "__main__":
    teams = load_teams()
    tbi = {t.id: t for t in teams}
    for y in (2024, 2025):
        run_year(y, teams, tbi)
