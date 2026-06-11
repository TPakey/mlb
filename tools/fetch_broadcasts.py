"""Per-Spiel-Broadcast-Daten von der MLB-Stats-API laden (C2 — Fakten statt Heuristik).

Läuft auf dem ENTWICKLER-RECHNER (volle Saison = zu groß für den
Sandbox-Fetcher):

    python -m tools.fetch_broadcasts                  # 2024 + 2025
    python -m tools.fetch_broadcasts --years 2024 2025 2026

Holt `hydrate=broadcasts(all)` mit Feld-Projektion (gamePk + nationale
TV-Sender) in Monats-Chunks und schreibt kompakte Fakten-Dateien
``data/mlb_broadcasts_<jahr>.json``: gamePk → Liste nationaler TV-CallSigns.
Damit wird die ESPN-Sunday-Night-Erkennung in
``src.start_times.load_exempt_pks`` FAKT (isNational + callSign ESPN) statt
Heuristik (Sonntag+Nacht+≥18:30). Quelle: statsapi.mlb.com (öffentlich).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

URL = ("https://statsapi.mlb.com/api/v1/schedule?sportId=1&gameType=R"
       "&startDate={start}&endDate={end}&hydrate=broadcasts(all)"
       "&fields=dates,date,games,gamePk,broadcasts,name,type,isNational,callSign")


def fetch_range(start: date, end: date) -> dict:
    url = URL.format(start=start.isoformat(), end=end.isoformat())
    req = urllib.request.Request(url, headers={"User-Agent": "mlb-logistics-optimizer"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_year(year: int) -> Path:
    national: dict = {}
    n_games = 0
    # Saisonfenster großzügig: Mitte März bis Anfang Oktober, Monats-Chunks.
    cur = date(year, 3, 10)
    season_end = date(year, 10, 5)
    while cur <= season_end:
        nxt = min(cur + timedelta(days=29), season_end)
        payload = fetch_range(cur, nxt)
        for day in payload.get("dates", []):
            for g in day.get("games", []):
                n_games += 1
                tv = sorted({b.get("callSign") or b.get("name", "?")
                             for b in g.get("broadcasts", [])
                             if b.get("type") == "TV" and b.get("isNational")})
                if tv:
                    national[str(g["gamePk"])] = tv
        print(f"  {cur}..{nxt}: kumuliert {len(national)} Spiele mit nationalem TV")
        cur = nxt + timedelta(days=1)
    out = {
        "_source": ("MLB Stats API schedule?hydrate=broadcasts(all), "
                    "fields-projiziert auf nationale TV-Broadcasts. "
                    "Abgerufen via tools/fetch_broadcasts.py. Rating: A "
                    "(offizielle API, faktisches isNational-Flag)."),
        "_season": year,
        "_n_games_scanned": n_games,
        "national_tv_by_game_pk": national,
    }
    target = DATA_DIR / f"mlb_broadcasts_{year}.json"
    target.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"  → {target} ({len(national)} Spiele mit nationalem TV)")
    return target


def main() -> int:
    p = argparse.ArgumentParser(description="Broadcast-Fakten laden (statsapi)")
    p.add_argument("--years", type=int, nargs="+", default=[2024, 2025])
    args = p.parse_args()
    ok = True
    for y in args.years:
        try:
            fetch_year(y)
        except Exception as exc:
            print(f"  FEHLER {y}: {exc}")
            ok = False
    if ok:
        print("\nFertig. SNB-Erkennung läuft jetzt faktenbasiert "
              "(src.start_times.load_exempt_pks bevorzugt die Fakten-Datei).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
