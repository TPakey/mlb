"""CLI: Flughafen- vs. Stadt-Koordinaten im Reisemodell vergleichen (P2-4).

Aufruf: python -m tools.compare_airport_distance [--season 2024]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data_loader import load_teams
from src.datasources import LocalFileAdapter
from src.airport_analysis import compare_airport_vs_city


def main() -> int:
    ap = argparse.ArgumentParser(description="Flughafen- vs. Stadt-Koordinaten")
    ap.add_argument("--season", type=int, default=2024)
    args = ap.parse_args()

    teams = load_teams()
    season = LocalFileAdapter(base_dir=str(ROOT / "data")).fetch_season_schedule(args.season)
    c = compare_airport_vs_city(season, teams)
    s = c.summary()

    print(f"Reisemodell-Vergleich {args.season} — Stadt vs. Flughafen")
    print(f"  Liga-Total Stadt:     {s['city_total_km']:>12,.0f} km")
    print(f"  Liga-Total Flughafen: {s['airport_total_km']:>12,.0f} km")
    print(f"  Differenz:            {s['delta_pct']:>+12.2f} %")
    print()
    print(f"  Anker-Fehler vs. publizierte MLB-Meilen (Ø |Fehler|):")
    print(f"    Stadt:     {s['anchor_city_abs_err_pct']:.2f} %")
    print(f"    Flughafen: {s['anchor_airport_abs_err_pct']:.2f} %")
    print()
    for tid, (pub, city, apk) in c.anchors.items():
        ce, ae = c.anchor_errors()[tid]
        print(f"    {tid}: publ={pub:>9,.0f}  Stadt={city:>9,.0f} ({ce:+.2f}%)  "
              f"Flughafen={apk:>9,.0f} ({ae:+.2f}%)")
    print()
    better = "Flughafen" if s['anchor_airport_abs_err_pct'] < s['anchor_city_abs_err_pct'] else "Stadt"
    print(f"  → Näher an publizierten Meilen (Ø): {better}. "
          f"Liga-Total-Differenz {s['delta_pct']:+.2f}% — marginal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
