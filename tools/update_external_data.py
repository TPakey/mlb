"""EIN Einstiegspunkt für alle externen Daten (Runde 3 — „top level").

Für den Alltagsbetrieb (MLB-Scheduler / Jonas' Rechner) bündelt dieses Tool
Beschaffung, Validierung und Messung der externen Datenquellen:

    python -m tools.update_external_data --all          # alles (Netz nötig)
    python -m tools.update_external_data --retrosheet   # Originalpläne (Gold)
    python -m tools.update_external_data --broadcasts   # nationale TV-Fakten
    python -m tools.update_external_data --measure-original   # offline Messung
    python -m tools.update_external_data --status       # was ist da, was fehlt

Jeder Schritt endet mit Messung/Validierung („messen statt behaupten"):
Retrosheet → Parse + Kreuzvalidierung gegen die statsapi-Rekonstruktion;
Broadcasts → Abdeckungszahlen; danach Manifest-Erneuerung für neue Dateien.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
MANIFEST = DATA_DIR / "MANIFEST.sha256.json"
YEARS = (2024, 2025)

sys.path.insert(0, str(REPO_ROOT))


def _add_to_manifest(rel_names) -> None:
    """Neue/aktualisierte Dateien ins Freeze-Manifest aufnehmen."""
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for name in rel_names:
        p = DATA_DIR / name
        if p.exists():
            man["files"][name] = hashlib.sha256(p.read_bytes()).hexdigest()
            print(f"  Manifest: {name} aufgenommen/erneuert")
    MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False),
                        encoding="utf-8")


def step_status() -> None:
    from src.original_schedule import has_retrosheet
    print("== Datenbestand ==")
    for y in YEARS + (2026,):
        retro = "✓" if has_retrosheet(y) else "fehlt (tools/fetch_retrosheet)"
        bc = DATA_DIR / f"mlb_broadcasts_{y}.json"
        bcs = "✓" if bc.exists() else ("Punkt-Fakten/Heuristik" if y in YEARS
                                       else "fehlt (tools/fetch_broadcasts)")
        sched = "✓" if (DATA_DIR / f"mlb_schedule_{y}.json").exists() else "fehlt"
        print(f"  {y}: statsapi={sched} | retrosheet={retro} | broadcasts={bcs}")
    print("== Referenz-/Registry-Dateien ==")
    for name, hint in (("cotenant_sharing.json", "C3-Registry (venueId-belegt)"),
                       ("forbes_team_financials_2025.json", "C1-Validierungsreferenz"),
                       ("mlb_national_tv.json", "Punkt-TV-Fakten"),
                       ("MANIFEST.sha256.json", "Freeze-Manifest")):
        ok = "✓" if (DATA_DIR / name).exists() else "FEHLT"
        print(f"  {name}: {ok}  ({hint})")
    print("  Vollständige Provenienz-Tabelle: docs/DATA_PROVENANCE.md")
    print("== Gurobi ==")
    try:
        from src.greenfield_gurobi import gurobi_status
        print(f"  {gurobi_status()}")
        print("  Einrichtung/Validierung: python -m tools.setup_gurobi")
    except Exception as exc:
        print(f"  nicht prüfbar: {exc}")


def step_retrosheet(years) -> bool:
    from tools.fetch_retrosheet import fetch_year
    from src.original_schedule import (load_retrosheet_schedule,
                                       reconstruct_original_schedule,
                                       cross_validate)
    ok = True
    for y in years:
        try:
            fetch_year(y)
            retro = load_retrosheet_schedule(y)
            stats = DATA_DIR / f"mlb_schedule_{y}.json"
            if stats.exists():
                recon = reconstruct_original_schedule(stats, season=y)
                diffs = cross_validate(retro, recon)
                print(f"  {y}: Kreuzvalidierung Retrosheet vs. Rekonstruktion: "
                      f"{len(diffs)} Abweichung(en)"
                      + (f", z. B. {diffs[0]}" if diffs else " ✓"))
        except Exception as exc:
            print(f"  FEHLER Retrosheet {y}: {exc}")
            ok = False
    return ok


def step_broadcasts(years) -> bool:
    from tools.fetch_broadcasts import fetch_year
    ok = True
    names = []
    for y in years:
        try:
            fetch_year(y)
            names.append(f"mlb_broadcasts_{y}.json")
        except Exception as exc:
            print(f"  FEHLER Broadcasts {y}: {exc}")
            ok = False
    if names:
        _add_to_manifest(names)
    return ok


def step_measure_original(years) -> bool:
    """Offline: Originalplan laden (Retrosheet bevorzugt) und die
    Originalplan-Regeln V(C)(13)/(14)/(15) darauf messen."""
    from src.original_schedule import load_original_schedule
    from src.schedule_rules import check_offday_distribution, check_doubleheader_limits
    for y in years:
        try:
            orig, quelle = load_original_schedule(y)
        except FileNotFoundError as exc:
            print(f"  {y}: {exc}")
            continue
        off = check_offday_distribution(orig)
        dh = check_doubleheader_limits(orig)
        print(f"  {y} [{quelle}] {len(orig.games)} Spiele: "
              f"V(C)(13)={len(off)}, V(C)(14/15)={len(dh)}")
        for v in (off + dh)[:8]:
            print(f"      {v.rule} {v.team}: {v.detail[:90]}")
    return True


def main() -> int:
    p = argparse.ArgumentParser(description="Externe Daten beschaffen + messen")
    p.add_argument("--all", action="store_true")
    p.add_argument("--retrosheet", action="store_true")
    p.add_argument("--broadcasts", action="store_true")
    p.add_argument("--cotenant", action="store_true",
                   help="C3: Co-Tenant-Kalender (Registry-getrieben) fetchen+validieren")
    p.add_argument("--measure-original", action="store_true")
    p.add_argument("--status", action="store_true")
    p.add_argument("--years", type=int, nargs="+", default=list(YEARS))
    args = p.parse_args()

    if not any((args.all, args.retrosheet, args.broadcasts, args.cotenant,
                args.measure_original, args.status)):
        args.status = True

    ok = True
    if args.status:
        step_status()
    if args.all or args.retrosheet:
        print("== Retrosheet (Originalpläne, Rating A) ==")
        ok &= step_retrosheet(args.years)
    if args.all or args.broadcasts:
        print("== Broadcast-Fakten (nationales TV) ==")
        ok &= step_broadcasts(args.years)
    if args.all or args.cotenant:
        print("== Co-Tenant-Kalender (C3) ==")
        import subprocess as _sp
        rc = _sp.call([sys.executable, "-m", "tools.fetch_cotenant_calendars",
                       "--years", *[str(y) for y in args.years]],
                      cwd=str(REPO_ROOT))
        ok &= (rc == 0)
    if args.all or args.retrosheet or args.measure_original:
        print("== Originalplan-Messung V(C)(13)/(14)/(15) ==")
        step_measure_original(args.years)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
