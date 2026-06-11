#!/usr/bin/env python3
"""What-if Demo — MLB Schedule Impact Analysis (Sprint 2.6).

Demonstriert alle drei What-if-Szenario-Typen in einer einzigen Pipeline:

  Szenario 1 — Force Series:
    NYY@BOS am 4. Juli 2026 (Independence Day Klassiker)
    → Wie viel Travel-Delta und Revenue-Effekt hat dieser Termin?

  Szenario 2 — Venue Blackout:
    Houston Astros (HOU): Konzert im Minute Maid Park am 15.–16. August 2026
    → Welche Serien müssen verschoben werden, was kostet das die Liga?

  Szenario 3 — Plan-Vergleich:
    Balanced-Plan vs. Travel-optimierter Plan aus der Pareto-Front
    → In welchen Dimensionen kauft man sich echte Verbesserung, welche verschlechtern sich?

Aufruf:
    python -m tools.whatif_demo                          # Standard (Seed 42)
    python -m tools.whatif_demo --seed 7 --sa-iter 5000
    python -m tools.whatif_demo --scenario force         # nur Szenario 1
    python -m tools.whatif_demo --scenario blackout      # nur Szenario 2
    python -m tools.whatif_demo --scenario compare       # nur Szenario 3
    python -m tools.whatif_demo --no-json                # kein JSON-Export
    python -m tools.whatif_demo --json-out output/my_whatif.json

Optionen:
    --seed INT           Master-Seed (default: 42)
    --sa-iter INT        SA-Iterationen für Pareto-Vergleich (default: 3000)
    --scenario STR       Nur ein bestimmtes Szenario laufen lassen (force/blackout/compare/all)
    --json-out PATH      JSON-Ausgabepfad (default: auto in output/)
    --no-json            Kein JSON-Export
    --verbose            Fortschritt-Ausgaben während der Saison-Generierung
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

# --- Pfad-Setup (funktioniert sowohl als Modul als auch direkt) -----------
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data_loader import load_teams
from src.datasources import LocalFileAdapter
from src.generator import GeneratorConfig, generate
from src.matchup_extractor import extract_matchup_quotas
from src.pareto import sample_pareto_frontier, ParetoFrontier
from src.player_fatigue import all_teams_pass_fatigue_constraints
from src.season import Season
from src.whatif import (
    WhatIfResult,
    analyze_team_impact,
    whatif_blackout,
    whatif_compare,
    whatif_force_series,
)


# =========================================================================
# Konsolen-Formatierung
# =========================================================================

WIDTH = 72


def _sep(char: str = "─") -> None:
    print(char * WIDTH)


def _header(title: str) -> None:
    _sep("═")
    print(f"  {title}")
    _sep("═")


def _subheader(title: str) -> None:
    print()
    _sep("─")
    print(f"  {title}")
    _sep("─")


def _print_result(result: WhatIfResult) -> None:
    """Gibt ein WhatIfResult formatiert auf stdout aus."""
    print(result.summary())
    if not result.feasible:
        print("  ⚠  Plan nicht vollständig feasibel — Details siehe Warnungen oben.")


def _fmt_time(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.1f}s"


# =========================================================================
# Baseline-Saison generieren
# =========================================================================

def _build_cfg(seed: int) -> GeneratorConfig:
    return GeneratorConfig(
        season=2026,
        season_start=date(2026, 3, 26),
        season_end=date(2026, 9, 27),
        all_star_break=(date(2026, 7, 13), date(2026, 7, 16)),
        max_solver_time_seconds=120,
        num_search_workers=1,
        random_seed=seed,
        enforce_fatigue_constraints=True,
    )


def _generate_season(cfg: GeneratorConfig, verbose: bool = False) -> "tuple[Season, list, list, float]":
    """Generiert eine Baseline-Saison.

    Returns:
        (season, teams, team_ids, elapsed_s)
    """
    adapter = LocalFileAdapter(base_dir=str(ROOT / "data"))
    season_2024 = adapter.fetch_season_schedule(2024)
    quotas = extract_matchup_quotas(season_2024)

    t0 = time.perf_counter()
    result = generate(quotas, cfg)
    elapsed = time.perf_counter() - t0

    if result.season is None:
        print(f"  FEHLER: CP-SAT lieferte Status '{result.status}'. Abbruch.", file=sys.stderr)
        sys.exit(1)

    teams = load_teams(cfg.teams_path)
    team_ids = [t.id for t in teams]

    if verbose:
        ok, _ = all_teams_pass_fatigue_constraints(result.season, team_ids)
        status_str = "✓" if ok else "✗"
        print(f"       Status    : {result.status}")
        print(f"       Spiele    : {len(result.season.games)}")
        print(f"       Travel    : {result.final_km:,.0f} km (nach SA)")
        print(f"       Fatigue   : {status_str} AC-2.1.8/9")
        print(f"       Zeit      : {_fmt_time(elapsed)}")

    return result.season, teams, team_ids, elapsed


# =========================================================================
# Szenario 1 — Force Series
# =========================================================================

def run_force_series(
    season: Season,
    teams: list,
    cfg: GeneratorConfig,
) -> WhatIfResult:
    """NYY@BOS am 4. Juli 2026 — Independence Day Klassiker."""
    _subheader("SZENARIO 1 — Force Series: NYY @ BOS am 4. Juli 2026")
    print()
    print("  Frage: Was passiert mit Travel, Revenue und Fatigue, wenn")
    print("  die New York Yankees am 4. Juli in Fenway Park spielen müssen?")
    print("  (MLB-Tradition: NYY@BOS zum Independence Day)")
    print()

    t0 = time.perf_counter()
    result = whatif_force_series(
        season=season,
        teams=teams,
        cfg=cfg,
        home="BOS",
        away="NYY",
        forced_start=date(2026, 7, 4),
        scenario_name="Force NYY@BOS — Independence Day 4. Juli",
    )
    elapsed = time.perf_counter() - t0
    print(f"  Laufzeit: {_fmt_time(elapsed)}")

    _print_result(result)

    # Detaillierter Team-Impact für NYY und BOS
    for team_id, label in [("NYY", "New York Yankees"), ("BOS", "Boston Red Sox")]:
        impact = analyze_team_impact(season, result.modified_season, team_id, teams=teams)
        if abs(impact.travel_delta_km) > 1 or impact.games_added or impact.games_removed:
            print(f"  Team-Impact {label} ({team_id}):")
            print(f"    Travel-Delta   : {impact.travel_delta_km:+.0f} km")
            print(f"    Heim-Delta     : {impact.home_games_delta:+d}")
            print(f"    Auswärts-Delta : {impact.away_games_delta:+d}")
            if impact.affected_series:
                print(f"    Betroffene Spiele (max 5):")
                for s in impact.affected_series[:5]:
                    print(f"      {s}")
            print()

    return result


# =========================================================================
# Szenario 2 — Venue Blackout
# =========================================================================

def run_blackout(
    season: Season,
    teams: list,
    cfg: GeneratorConfig,
) -> WhatIfResult:
    """HOU Venue-Blackout: Konzert im Minute Maid Park, 15.–16. Aug 2026."""
    _subheader("SZENARIO 2 — Venue Blackout: HOU Minute Maid Park, 15.–16. Aug 2026")
    print()
    print("  Frage: Ein Konzert im Minute Maid Park belegt das Stadion")
    print("  der Houston Astros am 15. und 16. August 2026.")
    print("  Welche Heimserien müssen verschoben werden, und was kostet das?")
    print()

    blackout_dates = [date(2026, 8, 15), date(2026, 8, 16)]
    t0 = time.perf_counter()
    result = whatif_blackout(
        season=season,
        teams=teams,
        cfg=cfg,
        team="HOU",
        blackout_dates=blackout_dates,
        is_home_blackout=True,
        reason="Konzert (Minute Maid Park, 15.–16. Aug 2026)",
        scenario_name="HOU Venue-Blackout — Konzert 15./16. Aug",
    )
    elapsed = time.perf_counter() - t0
    print(f"  Laufzeit: {_fmt_time(elapsed)}")

    _print_result(result)

    # Team-Impact für HOU
    impact = analyze_team_impact(season, result.modified_season, "HOU", teams=teams)
    print("  Team-Impact Houston Astros (HOU):")
    print(f"    Travel-Delta  : {impact.travel_delta_km:+.0f} km")
    print(f"    Heim-Delta    : {impact.home_games_delta:+d}")
    if impact.affected_series:
        print(f"    Betroffene Spiele (max 5):")
        for s in impact.affected_series[:5]:
            print(f"      {s}")
    print()

    return result


# =========================================================================
# Szenario 3 — Plan-Vergleich (Pareto)
# =========================================================================

def run_compare(
    season: Season,
    teams: list,
    team_ids: list,
    cfg: GeneratorConfig,
    sa_iter: int,
    seed: int,
) -> "tuple[WhatIfResult, Optional[ParetoFrontier]]":
    """Vergleicht den Balanced-Plan gegen den Travel-minimierten Pareto-Plan."""
    _subheader("SZENARIO 3 — Plan-Vergleich: Balanced vs. Travel-Optimiert (Pareto)")
    print()
    print("  Frage: Was gewinnt und verliert man wirklich, wenn man")
    print("  statt des ausgewogenen Plans den travel-minimierten Pareto-Plan wählt?")
    print(f"  (SA: {sa_iter} Iterationen pro Profil)")
    print()

    # Pareto-Front mit 2 Profilen berechnen (Balanced + Travel-Min)
    # Schnell: nur Anker (n_interior_points=0) → 6 Pläne in ~10s
    print("  Berechne Pareto-Front (6 Anker-Profile) …")
    t0 = time.perf_counter()

    frontier = sample_pareto_frontier(
        baseline_season=season,
        teams=teams,
        cfg=cfg,
        master_seed=seed,
        sa_iterations=sa_iter,
        sa_start_temperature=3_000_000.0,
        sa_end_temperature=100.0,
        sa_shift_max_days=7,
        n_interior_points=0,   # nur 6 Anker für schnelle Demo
    )
    pareto_time = time.perf_counter() - t0
    print(f"  Pareto-Zeit  : {_fmt_time(pareto_time)}")
    print(f"  Evaluiert    : {len(frontier.all_evaluated)} Pläne")
    print(f"  Nicht-dom.   : {frontier.n_non_dominated} Pläne")
    print()

    # balanced vs. travel_min aus der Pareto-Front holen
    balanced_point = frontier.best_by("travel_km")   # als Vergleichsreferenz
    travel_point = None
    for p in frontier.points:
        if "travel" in p.label.lower():
            travel_point = p
            break
    if travel_point is None:
        travel_point = frontier.best_by("travel_km")

    # Balanced: entweder benannter "balanced"-Plan oder Plan mit mittlerem Travel
    balanced_point_named = None
    for p in frontier.points:
        if "balanced" in p.label.lower():
            balanced_point_named = p
            break
    if balanced_point_named is None:
        # Median Travel wählen
        sorted_by_travel = sorted(frontier.points, key=lambda p: p.bundle.travel_km)
        mid = len(sorted_by_travel) // 2
        balanced_point_named = sorted_by_travel[mid]

    if balanced_point_named is None or travel_point is None:
        print("  Nicht genug Pareto-Punkte für Vergleich. Überspringe Szenario 3.")
        return None, frontier

    label_a = balanced_point_named.label
    label_b = travel_point.label

    print(f"  Vergleiche: '{label_a}' (Referenz) vs. '{label_b}' (Alternative)")
    t0 = time.perf_counter()

    result = whatif_compare(
        season_a=balanced_point_named.season,
        season_b=travel_point.season,
        teams=teams,
        label_a=label_a,
        label_b=label_b,
    )
    elapsed = time.perf_counter() - t0
    print(f"  Laufzeit     : {_fmt_time(elapsed)}")

    _print_result(result)

    # Übersicht Pareto-Front
    print("  ALLE PARETO-PLÄNE:")
    print(f"  {'Label':<22}  {'Travel':>12}  {'Revenue':>10}  {'Fatigue':>8}  {'TV-Score':>9}")
    _sep()
    for p in sorted(frontier.points, key=lambda x: x.bundle.travel_km):
        b = p.bundle
        marker = "★" if p.label in frontier.anchor_labels else " "
        print(
            f"  {marker}{p.label:<21}  "
            f"{b.travel_km:>11,.0f}  "
            f"${b.revenue_usd / 1e6:>8.1f}M  "
            f"{b.fatigue_score:>8.1f}  "
            f"{b.tv_slot_score:>9.1f}"
        )
    print()
    print("  ★ = Anker-Plan (benanntes Profil)")
    print()

    return result, frontier


# =========================================================================
# JSON-Export
# =========================================================================

def _result_to_json_entry(
    label: str,
    result: Optional[WhatIfResult],
    elapsed_s: float,
) -> dict:
    if result is None:
        return {"scenario": label, "status": "skipped"}
    return {
        "scenario": label,
        "elapsed_s": round(elapsed_s, 3),
        **result.to_dict(),
    }


def _export_json(
    out_path: Path,
    cfg: GeneratorConfig,
    gen_time: float,
    n_games: int,
    scenarios: List[dict],
) -> None:
    payload = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "season": cfg.season,
            "seed": cfg.random_seed,
            "generator_time_s": round(gen_time, 2),
            "n_games": n_games,
            "tool": "whatif_demo.py",
            "sprint": "2.6",
        },
        "scenarios": scenarios,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"  JSON-Export → {out_path}")


# =========================================================================
# Haupt-Demo
# =========================================================================

def run_demo(args: argparse.Namespace) -> None:
    total_start = time.perf_counter()

    _header(
        f"MLB WHAT-IF ENGINE — DEMO  (Sprint 2.6)  |  "
        f"Seed {args.seed}  |  Saison 2026"
    )
    print()

    run_all = args.scenario == "all"
    run_force    = run_all or args.scenario == "force"
    run_blkout   = run_all or args.scenario == "blackout"
    run_cmp      = run_all or args.scenario == "compare"

    # ------------------------------------------------------------------
    # Basis-Saison generieren (immer nötig)
    # ------------------------------------------------------------------
    print("  [SETUP] Generiere Baseline-Saison 2026 …")
    cfg = _build_cfg(args.seed)
    season, teams, team_ids, gen_time = _generate_season(cfg, verbose=args.verbose)
    n_games = len(season.games)
    if args.verbose:
        print()

    print(f"         Saison bereit: {n_games} Spiele, {_fmt_time(gen_time)}")
    print()

    # ------------------------------------------------------------------
    # Szenarien ausführen
    # ------------------------------------------------------------------
    scenario_results: List[dict] = []

    # Szenario 1
    force_result: Optional[WhatIfResult] = None
    force_time = 0.0
    if run_force:
        t0 = time.perf_counter()
        force_result = run_force_series(season, teams, cfg)
        force_time = time.perf_counter() - t0
        scenario_results.append(
            _result_to_json_entry("force_nyyatbos_jul4", force_result, force_time)
        )

    # Szenario 2
    blackout_result: Optional[WhatIfResult] = None
    blackout_time = 0.0
    if run_blkout:
        t0 = time.perf_counter()
        blackout_result = run_blackout(season, teams, cfg)
        blackout_time = time.perf_counter() - t0
        scenario_results.append(
            _result_to_json_entry("blackout_hou_aug15", blackout_result, blackout_time)
        )

    # Szenario 3
    compare_result: Optional[WhatIfResult] = None
    compare_time = 0.0
    frontier = None
    if run_cmp:
        t0 = time.perf_counter()
        compare_result, frontier = run_compare(
            season, teams, team_ids, cfg, sa_iter=args.sa_iter, seed=args.seed
        )
        compare_time = time.perf_counter() - t0
        scenario_results.append(
            _result_to_json_entry(
                "compare_balanced_vs_travel", compare_result, compare_time
            )
        )

    # ------------------------------------------------------------------
    # Zusammenfassung
    # ------------------------------------------------------------------
    total_time = time.perf_counter() - total_start
    print()
    _sep("═")
    print("  ZUSAMMENFASSUNG")
    _sep()
    if force_result:
        n_b, n_w = force_result.n_better, force_result.n_worse
        feas = "✓" if force_result.feasible else "✗"
        print(f"  Szenario 1 (Force NYY@BOS)  :  {n_b} besser, {n_w} schlechter  [{feas}]")
    if blackout_result:
        n_b, n_w = blackout_result.n_better, blackout_result.n_worse
        feas = "✓" if blackout_result.feasible else "✗"
        print(f"  Szenario 2 (HOU Blackout)   :  {n_b} besser, {n_w} schlechter  [{feas}]")
    if compare_result:
        n_b, n_w = compare_result.n_better, compare_result.n_worse
        print(f"  Szenario 3 (Plan-Vergleich)  :  {n_b} besser, {n_w} schlechter  [✓]")
    _sep()
    print(f"  Gesamtzeit: {_fmt_time(total_time)}")
    _sep("═")
    print()

    # ------------------------------------------------------------------
    # JSON-Export
    # ------------------------------------------------------------------
    if not args.no_json and scenario_results:
        if args.json_out:
            out_path = Path(args.json_out)
        else:
            out_dir = ROOT / "output"
            stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            out_path = out_dir / f"whatif_demo_{stamp}.json"

        _export_json(out_path, cfg, gen_time, n_games, scenario_results)
    elif args.no_json:
        print("  JSON-Export übersprungen (--no-json)")


# =========================================================================
# CLI
# =========================================================================

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="MLB What-if Engine Demo (Sprint 2.6)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Master-Seed für Reproduzierbarkeit",
    )
    p.add_argument(
        "--sa-iter",
        type=int,
        default=3000,
        dest="sa_iter",
        help="SA-Iterationen für Pareto-Vergleich (Szenario 3)",
    )
    p.add_argument(
        "--scenario",
        choices=["all", "force", "blackout", "compare"],
        default="all",
        help="Welches Szenario ausführen? (default: all)",
    )
    p.add_argument(
        "--json-out",
        type=str,
        default="",
        dest="json_out",
        help="JSON-Ausgabepfad (leer = automatischer Timestamp in output/)",
    )
    p.add_argument(
        "--no-json",
        action="store_true",
        dest="no_json",
        help="Kein JSON-Export",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Detaillierte Generierungs-Ausgabe",
    )
    return p.parse_args()


if __name__ == "__main__":
    run_demo(_parse_args())
