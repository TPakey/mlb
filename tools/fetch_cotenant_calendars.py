"""Co-Tenant-Kalender (C3) — config-getrieben fetchen, einpflegen, validieren.

Ersetzt das einmalige Einpflegen der River-Cats-Termine durch einen
REPRODUZIERBAREN Betriebspfad, den MLB-Ops jährlich (oder nach
MiLB-Spielplanänderungen) laufen lassen kann:

    python -m tools.fetch_cotenant_calendars                  # fetch + write + validate
    python -m tools.fetch_cotenant_calendars --years 2026
    python -m tools.fetch_cotenant_calendars --validate-only  # offline: Bestand prüfen

Quelle der Wahrheit ist ``data/cotenant_sharing.json`` (Registry, welcher
MLB-Club sich per venueId-Beleg ein Stadion mit welchem MiLB-Team teilt).
Für jeden Eintrag × Saison:
  1. MiLB-Heimspieltage von statsapi laden (sportId/teamId aus der Registry),
  2. zu Homestand-Blöcken verdichten,
  3. als ``stadium_booking``-Events idempotent in ``data/local_events.json``
     schreiben (alte Einträge desselben Schlüssels werden ersetzt; Schlüssel
     im ``note``-Feld: ``cotenant:<MLB>:<saison>``),
  4. VALIDIEREN: 0 Kollisionen mit dem realen MLB-Plan (as-played bzw.
     Retrosheet-Original, falls vorhanden) — sonst Exit 1,
  5. Manifest erneuern.

Deterministisch; Netz nur im Fetch-Schritt (``--validate-only`` ist offline).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path
from typing import List, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
REGISTRY = DATA_DIR / "cotenant_sharing.json"
EVENTS = DATA_DIR / "local_events.json"
MANIFEST = DATA_DIR / "MANIFEST.sha256.json"

sys.path.insert(0, str(REPO_ROOT))

SCHED_URL = ("https://statsapi.mlb.com/api/v1/schedule?sportId={sport}&teamId={team}"
             "&season={season}&gameType=R&startDate={season}-03-01&endDate={season}-10-01"
             "&fields=dates,date,games,teams,home,team,id")


def _load_registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def _note_key(mlb_team: str, season: int) -> str:
    return f"cotenant:{mlb_team}:{season}"


def fetch_home_dates(sport_id: int, team_id: int, season: int) -> List[date]:
    """Heimspieltage des MiLB-Teams (distinkte Kalendertage)."""
    url = SCHED_URL.format(sport=sport_id, team=team_id, season=season)
    req = urllib.request.Request(url, headers={"User-Agent": "mlb-logistics-optimizer"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    days: Set[date] = set()
    for day in payload.get("dates", []):
        d = date.fromisoformat(day["date"])
        for g in day.get("games", []):
            if g.get("teams", {}).get("home", {}).get("team", {}).get("id") == team_id:
                days.add(d)
    return sorted(days)


def to_blocks(days: List[date]) -> List[Tuple[date, date]]:
    """Konsekutive Tage → (start, end)-Blöcke (Homestands)."""
    if not days:
        return []
    blocks: List[Tuple[date, date]] = []
    start = prev = days[0]
    for d in days[1:]:
        if (d - prev).days > 1:
            blocks.append((start, prev))
            start = d
        prev = d
    blocks.append((start, prev))
    return blocks


def write_events(entry: dict, season: int, blocks: List[Tuple[date, date]],
                 n_days: int) -> None:
    """Events idempotent ersetzen (Schlüssel = note-Feld)."""
    raw = json.loads(EVENTS.read_text(encoding="utf-8"))
    key = _note_key(entry["mlb_team"], season)
    raw["events"] = [e for e in raw["events"]
                     if e.get("note") != key
                     # Migration: Alt-Einträge ohne note-Schlüssel (2026-06-11)
                     and not (entry["cotenant_name"].split()[-2] in e.get("name", "")
                              and e.get("start_date", "").startswith(str(season)))]
    for i, (a, b) in enumerate(blocks, 1):
        raw["events"].append({
            "city": entry.get("city", entry["venue"]),
            "team_ids": [entry["mlb_team"]],
            "name": (f"Co-Tenant {entry['cotenant_name']} Homestand "
                     f"{season}-{i:02d} ({entry['venue']})"),
            "start_date": a.isoformat(),
            "end_date": b.isoformat(),
            "severity": int(entry.get("severity", 5)),
            "category": "stadium_booking",
            "source": (f"MLB Stats API schedule?sportId={entry['cotenant_sport_id']}"
                       f"&teamId={entry['cotenant_team_id']}&season={season} "
                       f"(Rating A). venueId-Beleg: {entry['venue_id']}. "
                       f"Refresh: tools/fetch_cotenant_calendars. "
                       f"{n_days} Heimtage in {len(blocks)} Blöcken."),
            "note": key,
        })
    EVENTS.write_text(json.dumps(raw, indent=1, ensure_ascii=False), encoding="utf-8")


def validate(entry: dict, season: int) -> List[str]:
    """0-Kollisions-Beweis gegen den realen MLB-Plan (so weit Daten da sind)."""
    from src.event_conflicts import load_local_events, venue_conflicts
    problems: List[str] = []
    events = load_local_events()
    key = _note_key(entry["mlb_team"], season)
    mine = [e for e in events if e.note == key]
    has_ref = ((DATA_DIR / f"mlb_schedule_{season}.json").exists()
               or (DATA_DIR / "retrosheet" / f"{season}SKED.TXT").exists())
    if not mine:
        # Zukunftssaison ohne Referenzplan und ohne Events = noch nicht
        # eingepflegt (Info, kein Fehler); fehlen Events TROTZ Referenzplan,
        # ist der Bestand unvollstaendig (Fehler).
        if not has_ref:
            print(f"  ℹ {key}: noch nicht eingepflegt (Fetch noetig, "
                  f"kein Referenzplan vorhanden)")
            return []
        return [f"{key}: keine Events eingepflegt (Referenzplan vorhanden!)"]
    # Referenzplan: Retrosheet-Original bevorzugt, sonst as-played
    season_obj = None
    try:
        from src.original_schedule import load_retrosheet_schedule, has_retrosheet
        if has_retrosheet(season):
            season_obj = load_retrosheet_schedule(season)
            ref = "Retrosheet-Original"
    except Exception:
        pass
    if season_obj is None and (DATA_DIR / f"mlb_schedule_{season}.json").exists():
        from src.datasources.local_file import LocalFileAdapter
        season_obj = LocalFileAdapter(base_dir=DATA_DIR).fetch_season_schedule(season)
        ref = "as-played"
    if season_obj is None:
        return [f"{key}: kein Referenzplan zum Validieren (ok für Zukunftssaisons)"]
    conflicts = [c for c in venue_conflicts(season_obj, mine)
                 if c.team_id == entry["mlb_team"]]
    if conflicts:
        problems.append(
            f"{key}: {len(conflicts)} Kollision(en) mit {ref}-Plan — Daten oder "
            f"Registry prüfen! Erste: {conflicts[0].date} {conflicts[0].event_name}")
    else:
        print(f"  ✓ {key}: {len(mine)} Homestands, 0 Kollisionen mit {ref}-Plan")
    return problems


def _update_manifest() -> None:
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for name in ("local_events.json", "cotenant_sharing.json"):
        man["files"][name] = hashlib.sha256((DATA_DIR / name).read_bytes()).hexdigest()
    MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
    print("  Manifest erneuert (local_events.json, cotenant_sharing.json)")


def main() -> int:
    p = argparse.ArgumentParser(description="Co-Tenant-Kalender fetchen/validieren")
    p.add_argument("--years", type=int, nargs="+", default=None,
                   help="Default: alle Registry-Saisons mit lokalem Referenzplan +1")
    p.add_argument("--validate-only", action="store_true",
                   help="offline: nur Bestand in local_events.json validieren")
    args = p.parse_args()

    reg = _load_registry()
    problems: List[str] = []
    for entry in reg.get("sharing", []):
        years = args.years or entry["seasons"]
        years = [y for y in years if y in entry["seasons"]]
        for season in years:
            if not args.validate_only:
                days = fetch_home_dates(entry["cotenant_sport_id"],
                                        entry["cotenant_team_id"], season)
                if not days:
                    # Zukunftssaison: MiLB-Plan oft erst spaeter publiziert →
                    # Info. Vergangene/laufende Saison ohne Daten = Fehler.
                    if season > date.today().year:
                        print(f"  ℹ {entry['mlb_team']}/{season}: MiLB-Plan noch "
                              f"nicht publiziert — spaeter erneut fetchen")
                    else:
                        problems.append(f"{entry['mlb_team']}/{season}: 0 Heimtage "
                                        f"geliefert — API/Registry prüfen")
                    continue
                blocks = to_blocks(days)
                write_events(entry, season, blocks, len(days))
                print(f"  {entry['mlb_team']}/{season}: {len(days)} Heimtage → "
                      f"{len(blocks)} Homestand-Events geschrieben")
            problems += validate(entry, season)
    for n in reg.get("resolved_non_sharing", []):
        print(f"  ℹ kein Co-Tenant: {n['mlb_team']}/{n.get('season', '?')} — "
              f"{n['finding'][:80]}")
    if not args.validate_only:
        _update_manifest()
    if problems:
        print("\nPROBLEME:")
        for x in problems:
            print("  ✗", x)
        return 1
    print("OK — Co-Tenant-Kalender konsistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
