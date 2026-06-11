"""Validation-Harness CLI - vergleicht echten MLB-Plan mit optimaler Routenfuehrung.

Verwendung:
    python -m tools.validate_season --season 2024
    python -m tools.validate_season --season 2024 --season 2025
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data_loader import load_teams
from src.datasources import LocalFileAdapter
from src.legacy.validation import format_summary, result_to_dict, validate_season


def main() -> int:
    parser = argparse.ArgumentParser(description="Validation Harness")
    parser.add_argument("--season", type=int, action="append", required=True,
                        help="Saisonjahr (mehrfach moeglich)")
    parser.add_argument("--output-dir", default="output/validation",
                        help="Zielordner fuer Reports")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    data_dir = root / "data"
    out_dir = root / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    teams = load_teams()
    adapter = LocalFileAdapter(base_dir=data_dir)

    for year in args.season:
        if not args.quiet:
            print(f"\n=== Saison {year} ===")
        season = adapter.fetch_season_schedule(year)
        result = validate_season(season, teams)

        md = format_summary(result)
        md_path = out_dir / f"validation_{year}.md"
        md_path.write_text(md, encoding="utf-8")

        js = result_to_dict(result)
        js_path = out_dir / f"validation_{year}.json"
        js_path.write_text(json.dumps(js, indent=2), encoding="utf-8")

        if not args.quiet:
            print(f"Original km:   {result.total_km_original:>12,.0f}")
            print(f"Optimal km:    {result.total_km_optimal:>12,.0f}")
            print(f"Einsparung:    {result.total_savings_km:>12,.0f} km "
                  f"({result.savings_pct:.2f} %)")
            print(f"CO2-Einspar.:  {result.total_co2_savings_kg/1000:>12,.1f} t")
            print(f"USD-Einspar.:  {result.total_cost_savings_usd/1e6:>12,.2f} M")
            print(f"Report:        {md_path.relative_to(root)}")
            print(f"JSON:          {js_path.relative_to(root)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
