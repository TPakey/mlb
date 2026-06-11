"""Verifiziert eine heruntergeladene MLB-Stats-API-JSON-Datei.

Verwendung:
    python -m tools.inspect_schedule data/mlb_schedule_2024.json
"""
from __future__ import annotations

import sys
from pathlib import Path

# Pfad zum src-Modul finden
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.loaders import quick_diagnose


def main(path: str) -> int:
    p = Path(path)
    if not p.exists():
        print(f"FEHLER: Datei nicht gefunden: {p.resolve()}")
        return 2
    print(f"Pruefe: {p}")
    print(f"Groesse: {p.stat().st_size / 1024:.1f} KB\n")

    diag = quick_diagnose(p)
    if not diag["ok"]:
        print(f"FEHLER beim Laden: {diag['error']}")
        return 1

    print(f"Saison: {diag['season']}")
    stats = diag["stats"]
    print(f"\nStruktur:")
    print(f"  Teams gefunden:        {stats['teams']}")
    print(f"  Spiele total:          {stats['games_total']}")
    print(f"  Spiele/Team min..max:  {stats['games_per_team_min']}..{stats['games_per_team_max']}")
    print(f"  Heim/Team min..max:    {stats['home_per_team_min']}..{stats['home_per_team_max']}")
    print(f"  Doubleheader:          {stats['doubleheaders']}")
    print(f"  Erstes Spiel:          {stats['first_date']}")
    print(f"  Letztes Spiel:         {stats['last_date']}")

    if diag["unknown_home_team_codes"] or diag["unknown_away_team_codes"]:
        print(f"\n  WARNUNG: Unbekannte Team-Codes:")
        print(f"    Heim: {diag['unknown_home_team_codes']}")
        print(f"    Auswaerts: {diag['unknown_away_team_codes']}")

    print("\nValidierung:")
    expected_teams = 30
    expected_games = 2430   # 30 × 162 / 2
    ok_teams = stats["teams"] == expected_teams
    ok_total = abs(stats["games_total"] - expected_games) <= 10  # Toleranz für Doubleheader-Verschiebungen
    ok_per_team = 160 <= stats["games_per_team_min"] <= 164
    print(f"  {'OK' if ok_teams else 'FAIL'}  30 Teams gefunden ({stats['teams']})")
    print(f"  {'OK' if ok_total else 'FAIL'}  ~2430 Spiele gefunden ({stats['games_total']})")
    print(f"  {'OK' if ok_per_team else 'FAIL'}  ~162 Spiele pro Team ({stats['games_per_team_min']}..{stats['games_per_team_max']})")
    if ok_teams and ok_total and ok_per_team:
        print("\n=> Datei ist verwendbar. Naechster Schritt: Travel-Metriken berechnen.")
        return 0
    return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Verwendung: python -m tools.inspect_schedule <path-to-json>")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
