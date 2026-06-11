"""Messung Sprint 5.1 — V(C)(8)-Getaway-Formel gegen reale Startzeiten.

Lädt den realen Plan (2024/2025), extrahiert echte Startzeiten, identifiziert
Getaway-Spieltage und misst, ob die realen Startzeiten die V(C)(8)-Grenze
einhalten (Compliance) und wie nah sie an der Grenze liegen (Reproduktion).
Reine Messung — verändert nichts.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data_loader import load_teams, teams_by_id as _tbi
from src.datasources.local_file import LocalFileAdapter
from src.start_times import (
    AppendixC, find_getaway_contexts, load_real_start_times, fmt_min,
    validate_getaway_times, validate_nightday_times, validate_day_min_times,
    detect_home_openers, holiday_dates_for,
)


def measure(year: int) -> dict:
    teams = load_teams()
    tbi = _tbi(teams)
    ac = AppendixC.load()
    season = LocalFileAdapter(base_dir=ROOT / "data").fetch_season_schedule(year)
    real = load_real_start_times(ROOT / "data" / f"mlb_schedule_{year}.json", tbi)
    contexts = find_getaway_contexts(season, ac)

    by_key = {}
    for g in season.games:
        by_key.setdefault((g.date, g.home), []).append(g)

    total_getaway_games = 0
    binding = 0          # Getaway mit inflight > 2:30 (Grenze < 19:00 → real bindend)
    with_real = 0
    violations = []      # real start > latest
    at_cap = 0           # real start innerhalb 10 min unter der Grenze
    deltas = []          # latest - real (min), nur bindende Fälle mit realer Zeit
    for key, ctx in contexts.items():
        for g in by_key.get(key, []):
            total_getaway_games += 1
            is_binding = ctx.binding_inflight_min > 150
            if is_binding:
                binding += 1
            s = real.get(g.game_pk)
            if s is None:
                continue
            with_real += 1
            if s > ctx.latest_start_min:
                violations.append((g, ctx, s))
            if is_binding:
                deltas.append(ctx.latest_start_min - s)
                if 0 <= ctx.latest_start_min - s <= 10:
                    at_cap += 1

    print(f"\n===== {year} =====")
    print(f"Spiele gesamt: {len(season.games)}")
    print(f"Getaway-Spiele (V(C)(8) Folgetag-Reise): {total_getaway_games}")
    print(f"  davon bindend (inflight > 2:30): {binding}")
    print(f"  mit realer Startzeit: {with_real}")
    print(f"V(C)(8)-Verstöße (real > latest): {len(violations)}")
    if deltas:
        import statistics
        print(f"latest−real (bindende Fälle, n={len(deltas)}): "
              f"min={min(deltas)} median={int(statistics.median(deltas))} "
              f"max={max(deltas)} (Minuten; ≥0 = konform)")
        print(f"  real innerhalb 10 min unter der Grenze (am Cap): {at_cap}")
    # Bucket nach Überschreitung der Grenze (Konventions-Toleranz vs. echte Breach)
    excess = sorted(((s - ctx.latest_start_min, g, ctx) for g, ctx, s in violations),
                    key=lambda t: t[0])
    buckets = {"≤20min (7:05–7:20 Konvention)": 0, "21–40min": 0, ">40min": 0}
    for e, g, ctx in excess:
        if e <= 20:
            buckets["≤20min (7:05–7:20 Konvention)"] += 1
        elif e <= 40:
            buckets["21–40min"] += 1
        else:
            buckets[">40min"] += 1
    print("  Überschreitungs-Buckets:", buckets)
    print("  Größte Überschreitungen (Kandidaten für echte Breach / SNB / Reschedule):")
    for e, g, ctx in excess[-8:]:
        print(f"    +{e}min  {g.date} {g.away}@{g.home} pk={g.game_pk}: "
              f"real>{fmt_min(ctx.latest_start_min)} (inflight {fmt_min(ctx.binding_inflight_min)}, "
              f"reist {','.join(ctx.traveling)})")
    # V(C)(8) mit Konventions-Toleranz (per-Club 7:05–7:40 First-Pitch-Envelope)
    for tol in (0, 20, 40):
        v = validate_getaway_times(season, real, ac, tolerance_min=tol)
        print(f"  V(C)(8) Verstöße @tol={tol}min: {len(v)}")
    # V(C)(9) Tag-nach-Nacht (mit Feiertags-/Home-Opener-Ausnahmen)
    hol = holiday_dates_for(season)
    openers = detect_home_openers(season)
    v9 = validate_nightday_times(season, real, ac, tbi,
                                 holiday_dates=hol, home_opener_pks=openers)
    print(f"  V(C)(9) Verstöße (Tag<17:00 nach ≥19:00 Auswärts, m. Ausnahmen): {len(v9)}")
    for vv in v9[:6]:
        print(f"    {vv.detail} (pk={vv.game_pk}, {vv.game_date} @{vv.venue_team})")
    # V(C)(6) Tag-Spiel-Minimum
    v6 = validate_day_min_times(season, real)
    print(f"  V(C)(6) Verstöße (Tag-Spiel < 13:00 ohne Ausnahme): {len(v6)}")
    for vv in v6[:6]:
        print(f"    {vv.detail} (pk={vv.game_pk}, {vv.game_date} @{vv.venue_team})")
    return {
        "year": year, "getaway_games": total_getaway_games, "binding": binding,
        "with_real": with_real, "violations": len(violations), "at_cap": at_cap,
    }


if __name__ == "__main__":
    for y in (2024, 2025):
        measure(y)
