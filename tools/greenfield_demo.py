"""Green-field Gurobi-Demo (Sprint 5.4).

Zeigt den Lizenz-Status und löst eine reduzierte green-field Instanz from scratch.
Mit eingetragener akademischer Lizenz (.env: GRB_WLSACCESSID/SECRET/LICENSEID)
lassen sich größere Instanzen lösen — am Code ändert sich nichts.

    python -m tools.greenfield_demo --teams NYY,BOS,TBR,TOR --games-per-pair 2 --days 14
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data_loader import load_teams
from src.greenfield_gurobi import (
    gurobi_status, round_robin_instance, solve_greenfield, GurobiUnavailable,
)
from src.branch_and_price import branch_and_price
from src.greenfield_decomp import solve_greenfield_windowed
from src.ttp_rounds import solve_ttp_rounds, rounds_to_days


def main() -> int:
    ap = argparse.ArgumentParser(description="Green-field Gurobi-Demo")
    ap.add_argument("--teams", default="NYY,BOS,TBR",
                    help="Komma-separierte Team-IDs (klein halten ohne Voll-Lizenz)")
    ap.add_argument("--games-per-pair", type=int, default=2)
    ap.add_argument("--days", type=int, default=12)
    ap.add_argument("--max-consecutive", type=int, default=6)
    ap.add_argument("--time-limit", type=float, default=30.0)
    ap.add_argument("--method", choices=["monolithic", "bnp", "windowed", "rounds"],
                    default="monolithic",
                    help="monolithic = direktes Tag-MIP; bnp = Branch-and-Price; "
                         "windowed = Rolling-Horizon-Fenster; rounds = kompaktes "
                         "runden-/pattern-basiertes TTP-MIP (löst optimal, wo das "
                         "Tag-MIP zu groß wird; n muss gerade sein)")
    args = ap.parse_args()

    st = gurobi_status()
    print("Gurobi-Status:", st)
    if not st.get("available"):
        print("→ gurobipy installieren: pip install gurobipy --break-system-packages")
        return 1

    want = set(args.teams.split(","))
    teams = [t for t in load_teams() if t.id in want]
    if len(teams) < 2:
        print("Mindestens 2 gültige Team-IDs nötig.")
        return 1
    inst = round_robin_instance(teams, args.games_per_pair, args.days,
                                max_consecutive=args.max_consecutive)
    print(f"\nLöse green-field ({args.method}): {len(teams)} Teams, "
          f"{args.games_per_pair} Spiele/Paar, {args.days} Tage ...")
    try:
        if args.method == "bnp":
            res = branch_and_price(inst, max_cg_iter=10,
                                   pricing_time_s=min(10.0, args.time_limit))
            extra = (f" | Spalten: {res.n_columns} | CG-Iter: {res.cg_iterations}"
                     f" | Bootstrap-km: {res.bootstrap_km:,.1f}")
        elif args.method == "rounds":
            res = solve_ttp_rounds(teams, games_per_pair=args.games_per_pair,
                                   max_road_trip=3, time_limit_s=args.time_limit)
            extra = f" | Runden: {res.n_rounds} | gap: {res.gap}"
            if res.rounds:
                res.games = rounds_to_days(res.rounds, day_gap=2)
        elif args.method == "windowed":
            res = solve_greenfield_windowed(inst, window_days=max(4, args.days // 3),
                                            passes=2,
                                            window_time_s=min(10.0, args.time_limit))
            extra = (f" | Fenster: {res.n_windows} | Pässe: {res.passes}"
                     f" | Bootstrap-km: {res.bootstrap_km:,.1f}")
        else:
            res = solve_greenfield(inst, time_limit_s=args.time_limit)
            extra = ""
    except GurobiUnavailable as exc:
        print(f"\n⚠ {exc}")
        print("→ Für größere Instanzen die akademische Lizenz in .env eintragen "
              "(GRB_WLSACCESSID/GRB_WLSSECRET/GRB_LICENSEID).")
        return 1
    print(f"Status: {res.status} | Reise-km: "
          f"{res.objective_km:,.1f} | Laufzeit: {res.runtime_s:.2f}s | "
          f"Spiele: {len(res.games)}{extra}")
    for d, h, a in res.games:
        print(f"  Tag {d:>2}: {a} @ {h}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
