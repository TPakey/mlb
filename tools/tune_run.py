"""CLI: eine Tuner-Konfiguration rechnen und echte Zahlen ausgeben (Sprint 3).

Nimmt die JSON, die dashboard/phase_tuner.html exportiert
({"profile_weights": {...}, "phase_plan": {"phases": [...]}}), startet vom realen
Plan und liefert die tatsaechlichen Kennzahlen — global vs. realer MLB-Plan plus
pro-Fenster.

    python -m tools.tune_run --config meine_config.json --season 2024
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tools.tuning import evaluate_tuning


def _fmt(v: float, unit: str = "") -> str:
    return f"{v:,.0f}{unit}"


def main() -> int:
    p = argparse.ArgumentParser(description="Tuner-Konfiguration rechnen (echte Zahlen)")
    p.add_argument("--config", required=True, help="Export-JSON aus phase_tuner.html")
    p.add_argument("--season", type=int, default=2024)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--pareto-iterations", type=int, default=80_000)
    p.add_argument("--json-out", default=None, help="Ergebnis zusaetzlich als JSON speichern")
    args = p.parse_args()

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    res = evaluate_tuning(
        profile_weights=cfg.get("profile_weights", {}),
        phase_plan_dict=cfg.get("phase_plan"),
        season_year=args.season,
        seed=args.seed,
        pareto_iterations=args.pareto_iterations,
    )

    d = res["dimensions"]
    print(f"\n=== Tuner-Ergebnis (Saison {args.season}, Seed {args.seed}) ===")
    print(f"{'Dimension':<20} {'realer Plan':>16} {'unser Plan':>16} {'Δ %':>8}  Urteil")
    labels = {
        "travel_km": ("Reise", " km"), "revenue_usd": ("Revenue", " $"),
        "fatigue_score": ("Fatigue", ""), "max_away_streak": ("Auswärts-Streak", " T"),
        "tv_slot_score": ("TV-Score", ""), "event_friction": ("Friction", ""),
        "constraint_violations": ("CBA-Verletzungen", ""),
    }
    for k, (lbl, unit) in labels.items():
        row = d[k]
        pct = f"{row['pct']:+.1f}%" if row["pct"] is not None else "—"
        print(f"{lbl:<20} {_fmt(row['real'], unit):>16} {_fmt(row['ours'], unit):>16} {pct:>8}  {row['verdict']}")

    if res["windows"]:
        print("\n=== Pro-Fenster (Phasen) ===")
        for w in res["windows"]:
            o, r = w["optimized"], w["real"]
            tvd = (o["tv_slot_score"] - r["tv_slot_score"])
            print(f"  {w['name']} ({w['start']}..{w['end']}) mult={w['multipliers']}")
            print(f"    TV: real {r['tv_slot_score']:.1f} → unser {o['tv_slot_score']:.1f} "
                  f"({tvd:+.1f}) · Revenue: {o['revenue_usd']:,.0f} $ · {o['games']} Spiele")

    s = res["summary"]
    print(f"\nZusammenfassung: Reise {s['travel_km']:,.0f} km "
          f"({s['travel_vs_real_pct']:+.1f}% vs real) · "
          f"CBA-konform: {'JA' if s['cba_compliant'] else 'NEIN'} "
          f"({s['constraint_violations']} Verletzungen)")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(res, indent=2), encoding="utf-8")
        print(f"\nJSON gespeichert: {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
