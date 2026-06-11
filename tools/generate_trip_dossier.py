"""CLI: operatives Trip-Dossier für ein Team generieren (Scheduler-Ops).

Aufruf:
    python -m tools.generate_trip_dossier --team NYY --season 2024
    python -m tools.generate_trip_dossier --team NYY --season 2024 --limit 5 --out output/ops/NYY_2024.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.datasources import LocalFileAdapter
from src.ops_dossier import team_trip_dossiers, team_dossier_report


def main() -> int:
    ap = argparse.ArgumentParser(description="MLB Trip-Operations-Dossier")
    ap.add_argument("--team", required=True, help="Team-ID (z.B. NYY)")
    ap.add_argument("--season", type=int, default=2024)
    ap.add_argument("--limit", type=int, default=None,
                    help="Nur die ersten N Auswärts-Städte")
    ap.add_argument("--out", default=None, help="Markdown-Zielpfad")
    args = ap.parse_args()

    season = LocalFileAdapter(base_dir=str(ROOT / "data")).fetch_season_schedule(args.season)
    dossiers = team_trip_dossiers(season, args.team, limit=args.limit)
    md = team_dossier_report(season, args.team, dossiers=dossiers)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print(f"Dossier geschrieben: {out} ({len(dossiers)} Städte)")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
