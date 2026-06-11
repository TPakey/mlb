"""Schedule-Daten abrufen und ins Filesystem schreiben.

Versucht die Online-Adapter (SportsDataIO); falls Netzwerk nicht verfügbar,
wird eine genaue Anleitung gedruckt, wie der Nutzer die Datei manuell holt.

Verwendung:
    python -m tools.fetch_schedule --season 2024
    python -m tools.fetch_schedule --season 2024 --source sportsdataio
    python -m tools.fetch_schedule --season 2024 --print-curl   # nur den Befehl
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_sportsdataio_key
from src.datasources import DataSourceError, LocalFileAdapter, SportsDataIoAdapter


def _print_manual_instructions(season: int, key: str | None) -> None:
    target = f"data/sportsdataio_games_{season}.json"
    print(f"\n--- Manueller Download nötig ---")
    print(f"Führe auf deiner Maschine aus (nicht im Sandbox):\n")
    if key:
        masked = key[:4] + "…" + key[-4:]
        print(f"  Key in .env gefunden ({masked}).")
        print(f"  curl 'https://api.sportsdata.io/v3/mlb/scores/json/Games/{season}?key={key}' \\")
    else:
        print(f"  KEY=<dein-sportsdataio-key>")
        print(f"  curl \"https://api.sportsdata.io/v3/mlb/scores/json/Games/{season}?key=$KEY\" \\")
    print(f"    -o '{target}'\n")
    print(f"Danach:")
    print(f"  python -m tools.inspect_schedule {target}")


def main() -> int:
    parser = argparse.ArgumentParser(description="MLB Schedule-Daten abrufen")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--source", choices=["sportsdataio", "local"], default="sportsdataio")
    parser.add_argument("--print-curl", action="store_true",
                        help="Nur den curl-Befehl drucken, keinen Online-Versuch")
    args = parser.parse_args()

    data_dir = Path(__file__).resolve().parent.parent / "data"
    key = get_sportsdataio_key()

    if args.print_curl:
        _print_manual_instructions(args.season, key)
        return 0

    if args.source == "local":
        adapter = LocalFileAdapter(base_dir=data_dir)
        try:
            season = adapter.fetch_season_schedule(args.season)
        except DataSourceError as e:
            print(f"FEHLER: {e}")
            return 1
        print(f"Geladen aus lokaler Datei: {season.stats()}")
        return 0

    # source == sportsdataio
    if not key:
        print("FEHLER: SPORTSDATAIO_MLB_KEY ist nicht gesetzt. Trage ihn in .env ein.")
        return 2

    adapter = SportsDataIoAdapter(api_key=key, cache_dir=data_dir)
    try:
        season = adapter.fetch_season_schedule(args.season)
    except DataSourceError as e:
        print(f"Online-Abruf fehlgeschlagen: {e}")
        _print_manual_instructions(args.season, key)
        return 1

    print(f"Erfolg. Saison {args.season}: {season.stats()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
