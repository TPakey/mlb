"""Retrosheet-Original-Schedules herunterladen (Goldquelle für P1-5).

Läuft auf dem ENTWICKLER-RECHNER (normales Netz; die Review-Sandbox kann keine
ZIP-Binärdaten transportieren — deshalb dieses Tool statt Handarbeit):

    python -m tools.fetch_retrosheet                  # 2024 + 2025 + 2026
    python -m tools.fetch_retrosheet --years 2024 2025

Lädt https://www.retrosheet.org/schedule/<JAHR>SKED.zip, entpackt die
SKED.TXT nach data/retrosheet/, schreibt den lizenzpflichtigen Quellenvermerk
(Retrosheet-Bedingung) und erneuert die Manifest-Einträge. Danach bevorzugt
src/original_schedule.load_original_schedule automatisch Retrosheet (Rating A)
und kreuzvalidiert gegen die statsapi-Rekonstruktion (Rating B).
"""
from __future__ import annotations

import argparse
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "retrosheet"
BASE_URL = "https://www.retrosheet.org/schedule/{year}SKED.zip"

# Pflicht-Vermerk laut retrosheet.org (Bedingung der freien Nutzung):
NOTICE = """Retrosheet-Daten — Pflicht-Quellenvermerk
==========================================
The information used here was obtained free of charge from and is
copyrighted by Retrosheet. Interested parties may contact Retrosheet
at 20 Sunset Rd., Newark, DE 19711.

Quelle: https://www.retrosheet.org/schedule/ (Original Regular Season
Schedules). Abgerufen via tools/fetch_retrosheet.py. Provenienz-Rating: A
(publiziertes Original inkl. Postponement-/Makeup-Vermerken).
"""


def fetch_year(year: int) -> Path:
    url = BASE_URL.format(year=year)
    print(f"  Lade {url} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "mlb-logistics-optimizer"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        blob = resp.read()
    zf = zipfile.ZipFile(io.BytesIO(blob))
    names = [n for n in zf.namelist() if n.upper().endswith((".TXT", ".CSV"))]
    if not names:
        raise RuntimeError(f"{url}: keine TXT/CSV im Archiv ({zf.namelist()})")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUT_DIR / f"{year}SKED.TXT"
    target.write_bytes(zf.read(names[0]))
    print(f"  → {target} ({target.stat().st_size:,} Bytes aus {names[0]})")
    return target


def main() -> int:
    p = argparse.ArgumentParser(description="Retrosheet-Original-Schedules laden")
    p.add_argument("--years", type=int, nargs="+", default=[2024, 2025, 2026])
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "README.txt").write_text(NOTICE, encoding="utf-8")
    ok = True
    for y in args.years:
        try:
            target = fetch_year(y)
            # Sofort-Validierung: parsen + Spielzahl pruefen
            sys.path.insert(0, str(REPO_ROOT))
            from src.original_schedule import load_retrosheet_schedule
            season = load_retrosheet_schedule(y, path=target)
            print(f"  Validiert: {len(season.games)} Spiele, "
                  f"{season.season_start}..{season.season_end}")
        except Exception as exc:
            print(f"  FEHLER {y}: {exc}")
            ok = False
    if ok:
        print("\nFertig. Kreuzvalidierung + Originalplan-Messung:")
        print("  python -m tools.update_external_data --measure-original")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
