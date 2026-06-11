#!/usr/bin/env python3
"""End-to-End Demo: MLB Schedule Pareto-Optimierung (Sprint 2.4).

Zeigt den vollen Pipeline-Durchlauf für MLB-Stakeholder:
  1. Saison 2026 generieren (CP-SAT + Travel-SA, ~20s)
  2. Pareto-Front über 8 Dimensionen berechnen (Anker + Interior-Punkte)
  3. Kompakte Ergebnis-Tabelle auf stdout
  4. JSON-Export nach output/pareto_demo_YYYY-MM-DD.json

Aufruf:
    python -m tools.demo_pareto                 # Standard (Seed 42, schnell)
    python -m tools.demo_pareto --iterations 10000 --interior 6
    python -m tools.demo_pareto --json-out output/mein_ergebnis.json

Optionen:
    --seed INT           Master-Seed (default: 42)
    --sa-iter INT        SA-Iterationen pro Pareto-Lauf (default: 3000)
    --interior INT       Anzahl Interior-Punkte (default: 4)
    --shift INT          SA shift_max_days (default: 7)
    --json-out PATH      JSON-Ausgabepfad (default: auto in output/)
    --no-json            Kein JSON-Export
    --verbose            Detailliertes SA-Log
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path

# --- Pfad-Setup (funktioniert sowohl als Modul als auch direkt) -----------
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data_loader import load_teams
from src.datasources import LocalFileAdapter
from src.generator import GeneratorConfig, generate
from src.matchup_extractor import extract_matchup_quotas
from src.pareto import sample_pareto_frontier, ParetoFrontier
from src.player_fatigue import all_teams_pass_fatigue_constraints


# =========================================================================
# Hilfsfunktionen
# =========================================================================

def _fmt_km(km: float) -> str:
    return f"{km:>12,.0f} km"


def _fmt_usd(usd: float) -> str:
    return f"${usd / 1_000_000:>8.1f}M"


def _fmt_score(x: float) -> str:
    return f"{x:>10.1f}"


def print_separator(char: str = "─", width: int = 72) -> None:
    print(char * width)


def print_frontier_table(frontier: ParetoFrontier) -> None:
    """Druckt eine kompakte Tabelle der Pareto-Front."""
    print()
    print_separator("═")
    print(f"  PARETO-FRONT — {frontier.n_non_dominated} nicht-dominierte Pläne"
          f"  (von {len(frontier.all_evaluated)} evaluiert)")
    print_separator("═")

    # Header
    print(
        f"  {'Label':<18}  {'Travel':>13}  {'Revenue':>10}  "
        f"{'Fatigue':>10}  {'MaxAway':>8}  {'TV-Score':>9}  "
        f"{'Friction':>9}"
    )
    print_separator()

    for p in sorted(frontier.points, key=lambda x: x.bundle.travel_km):
        b = p.bundle
        is_anchor = p.label in frontier.anchor_labels
        marker = "★" if is_anchor else " "
        print(
            f"  {marker}{p.label:<17}  "
            f"{_fmt_km(b.travel_km)}  "
            f"{_fmt_usd(b.revenue_usd)}  "
            f"{_fmt_score(b.fatigue_score)}  "
            f"{b.max_away_streak:>8.1f}  "
            f"{_fmt_score(b.tv_slot_score)}  "
            f"{_fmt_score(b.event_friction)}"
        )

    print_separator()
    print("  ★ = Anker-Plan (benanntes Profil)")
    print()

    # Beste pro Dimension
    print("  BEST-IN-CLASS:")
    dims = [
        ("travel_km",       "Travel (min)",      True),
        ("revenue_usd",     "Revenue (max)",     False),
        ("fatigue_score",   "Fatigue (min)",     True),
        ("max_away_streak", "Max-Away (min)",    True),
        ("tv_slot_score",   "TV-Score (max)",    False),
        ("event_friction",  "Friction (min)",    True),
    ]
    for dim, label, _ in dims:
        best = frontier.best_by(dim)
        if best:
            print(f"    {label:<20} → {best.label}")
    print()


def print_fatigue_summary(season, team_ids) -> None:
    """Gibt kurz aus, ob AC-2.1.8/9 im Baseline-Plan eingehalten sind."""
    ok, viols = all_teams_pass_fatigue_constraints(season, team_ids)
    if ok:
        print("  ✓  Baseline-Plan: AC-2.1.8 & AC-2.1.9 eingehalten (alle 30 Teams)")
    else:
        print(f"  ✗  Baseline-Plan: {len(viols)} Constraint-Verletzung(en):")
        for v in viols[:5]:
            print(f"       {v}")
        if len(viols) > 5:
            print(f"       ... (+{len(viols) - 5} weitere)")
    print()


# =========================================================================
# Haupt-Demo
# =========================================================================

def run_demo(args: argparse.Namespace) -> None:
    total_start = time.perf_counter()

    print()
    print_separator("═")
    print("  MLB SCHEDULE OPTIMIZER — PARETO DEMO  (Sprint 2.4)")
    print(f"  Saison 2026  |  Seed {args.seed}  |  "
          f"{args.sa_iter} SA-Iter/Profil  |  {args.interior} Interior-Punkte")
    print_separator("═")
    print()

    # ------------------------------------------------------------------
    # 1. Daten laden + Saison generieren
    # ------------------------------------------------------------------
    print("  [1/3] Generiere Baseline-Saison 2026 …")
    t0 = time.perf_counter()

    adapter = LocalFileAdapter(base_dir=str(ROOT / "data"))
    season_2024 = adapter.fetch_season_schedule(2024)
    quotas = extract_matchup_quotas(season_2024)

    cfg = GeneratorConfig(
        season=2026,
        season_start=date(2026, 3, 26),
        season_end=date(2026, 9, 27),
        all_star_break=(date(2026, 7, 13), date(2026, 7, 16)),
        max_solver_time_seconds=120,
        num_search_workers=1,
        random_seed=args.seed,
        enforce_fatigue_constraints=True,
    )

    result = generate(quotas, cfg)
    gen_time = time.perf_counter() - t0

    if result.season is None:
        print(f"  FEHLER: CP-SAT lieferte Status '{result.status}'. Abbruch.")
        sys.exit(1)

    n_games = len(result.season.games)
    print(f"       Status : {result.status}")
    print(f"       Spiele : {n_games}")
    print(f"       Travel : {result.final_km:,.0f} km (nach SA)")
    print(f"       Zeit   : {gen_time:.1f}s")
    print()

    teams = load_teams(cfg.teams_path)
    team_ids = [t.id for t in teams]
    print_fatigue_summary(result.season, team_ids)

    # ------------------------------------------------------------------
    # 2. Pareto-Front berechnen
    # ------------------------------------------------------------------
    print(f"  [2/3] Berechne Pareto-Front ({len(teams)}-Team-Liga) …")
    if args.verbose:
        print("        (--verbose: SA-Log folgt)")
    print()
    t0 = time.perf_counter()

    frontier = sample_pareto_frontier(
        baseline_season=result.season,
        teams=teams,
        cfg=cfg,
        master_seed=args.seed,
        sa_iterations=args.sa_iter,
        sa_start_temperature=3_000_000.0,
        sa_end_temperature=100.0,
        sa_shift_max_days=args.shift,
        n_interior_points=args.interior,
        verbose=args.verbose,
    )
    pareto_time = time.perf_counter() - t0
    print(f"       Pareto-Zeit : {pareto_time:.1f}s")
    print(f"       Evaluiert   : {len(frontier.all_evaluated)} Pläne")
    print(f"       Nicht-dom.  : {frontier.n_non_dominated} Pläne")

    # ------------------------------------------------------------------
    # 3. Ergebnisse ausgeben
    # ------------------------------------------------------------------
    print_frontier_table(frontier)

    # ------------------------------------------------------------------
    # 4. JSON-Export
    # ------------------------------------------------------------------
    if not args.no_json:
        out_dir = ROOT / "output"
        out_dir.mkdir(exist_ok=True)

        if args.json_out:
            out_path = Path(args.json_out)
        else:
            stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            out_path = out_dir / f"pareto_demo_{stamp}.json"

        payload = {
            "meta": {
                "generated_at": datetime.now().isoformat(),
                "season": cfg.season,
                "seed": args.seed,
                "sa_iterations_per_profile": args.sa_iter,
                "n_interior_points": args.interior,
                "generator_status": result.status,
                "n_games": n_games,
                "baseline_km": result.final_km,
                "gen_time_s": round(gen_time, 2),
                "pareto_time_s": round(pareto_time, 2),
                "total_time_s": round(time.perf_counter() - total_start, 2),
            },
            "frontier": frontier.to_dict(),
        }
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"  [3/3] JSON-Export → {out_path.relative_to(ROOT)}")
    else:
        print("  [3/3] JSON-Export übersprungen (--no-json)")

    total_time = time.perf_counter() - total_start
    print()
    print_separator("═")
    print(f"  FERTIG  |  Gesamtzeit: {total_time:.1f}s")
    print_separator("═")
    print()


# =========================================================================
# CLI
# =========================================================================

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="MLB Schedule Pareto-Demo (Sprint 2.4)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--seed",      type=int, default=42,   help="Master-Seed")
    p.add_argument("--sa-iter",   type=int, default=3000, help="SA-Iterationen pro Pareto-Profil")
    p.add_argument("--interior",  type=int, default=4,    help="Anzahl Interior-Punkte")
    p.add_argument("--shift",     type=int, default=7,    help="SA shift_max_days")
    p.add_argument("--json-out",  type=str, default="",   help="JSON-Ausgabepfad (leer = auto)")
    p.add_argument("--no-json",   action="store_true",    help="Kein JSON-Export")
    p.add_argument("--verbose",   action="store_true",    help="Detailliertes SA-Log")
    return p.parse_args()


if __name__ == "__main__":
    run_demo(_parse_args())
