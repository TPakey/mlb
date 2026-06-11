"""Sprint 5.2 — Strukturelle Article-V-Regeln auf Schedule-Ebene.

Ergänzt `compliance.py` um die CBA-Regeln, die **nicht** Reise-/Startzeit-, sondern
**Originalplan-Struktur** betreffen:

- **V(C)(13)** Off-Day-Verteilung (≤2 Open Days / 7-Tage-Fenster; ≥7 in den letzten 67
  Tagen; ≥3 in den letzten 32).
- **V(C)(14)/(15)** Doubleheader-Limits (keine DH an Folgetagen; Twi-Night-DH ≤3 je
  Heimclub und nicht am Getaway-Tag).

**Wichtige Datensemantik (Ehrlichkeit):** Diese Regeln gelten für den *Originalplan*
(„original schedule"). Die `data/mlb_schedule_{2024,2025}.json` sind **as-played**
(Makeups/Rainouts/Relokationen/internationale Serien) → enthalten Artefakt-DHs und
Artefakt-Off-Day-Fenster, die KEINE echten Regelverstöße sind. Deshalb sind diese
Checks als **Guard auf sauberen (Optimierer-/Original-)Plänen** gedacht; auf
as-played-Daten liefern sie eine *informative* Messung, keine harte Bewertung
(`schedule_kind="as_played"` → soft; `"original"` → hart). Siehe `finding-as-played-data`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional

from .season import Season, detect_all_star_break


@dataclass(frozen=True)
class StructuralViolation:
    rule: str           # "V(C)(13)" | "V(C)(14)" | "V(C)(15)"
    team: str
    detail: str


# ====================================================================
# V(C)(13) — Off-Day-Verteilung
# ====================================================================

def _team_open_days(season: Season, team: str,
                    exclude: Optional[set] = None) -> List[date]:
    """Open Days eines Teams (Tage ohne Spiel zwischen erstem/letztem Spieltag),
    optional unter Ausschluss von Datumsmengen (z. B. All-Star-Break)."""
    exclude = exclude or set()
    return [d for d in season.off_days(team) if d not in exclude]


def check_offday_distribution(
    season: Season,
    team_ids: Optional[List[str]] = None,
    *,
    max_per_7: int = 2,
    min_last_67: int = 7,
    min_last_32: int = 3,
) -> List[StructuralViolation]:
    """V(C)(13): Off-Day-Verteilung pro Team.

    - **≤ max_per_7 Open Days in jedem 7-Tage-Fenster** — der All-Star-Break (V(C)(17),
      4 Tage) ist eine geplante Liga-Pause und wird aus der Zählung ausgenommen
      (sonst würde jedes ASB-überlappende Fenster fälschlich anschlagen).
    - **≥ min_last_67 Open Days in den letzten 67 Tagen** der Saison.
    - **≥ min_last_32 Open Days in den letzten 32 Tagen**.
    """
    if team_ids is None:
        team_ids = sorted({g.home for g in season.games} | {g.away for g in season.games})
    asb = detect_all_star_break(season)
    asb_days = set()
    if asb:
        d = asb[0]
        while d <= asb[1]:
            asb_days.add(d)
            d += timedelta(days=1)

    viols: List[StructuralViolation] = []
    for t in team_ids:
        gs = season.games_for_team(t)
        if not gs:
            continue
        first, last = gs[0].date, gs[-1].date
        opens = set(_team_open_days(season, t, exclude=asb_days))
        # ≤ max_per_7 in jedem rollierenden 7-Tage-Fenster
        worst = 0
        worst_win = None
        d = first
        while d <= last - timedelta(days=6):
            cnt = sum(1 for k in range(7) if (d + timedelta(days=k)) in opens)
            if cnt > worst:
                worst, worst_win = cnt, d
            d += timedelta(days=1)
        if worst > max_per_7:
            viols.append(StructuralViolation(
                "V(C)(13)", t,
                f"{worst} Open Days im 7-Tage-Fenster ab {worst_win} (Limit {max_per_7}, "
                f"ASB ausgenommen)"))
        # ≥ min_last_67 in den letzten 67 Tagen
        last67 = sum(1 for o in opens if o > last - timedelta(days=67))
        if last67 < min_last_67:
            viols.append(StructuralViolation(
                "V(C)(13)", t,
                f"nur {last67} Open Days in den letzten 67 Tagen (min {min_last_67})"))
        # ≥ min_last_32 in den letzten 32 Tagen
        last32 = sum(1 for o in opens if o > last - timedelta(days=32))
        if last32 < min_last_32:
            viols.append(StructuralViolation(
                "V(C)(13)", t,
                f"nur {last32} Open Days in den letzten 32 Tagen (min {min_last_32})"))
    return viols


# ====================================================================
# V(C)(14)/(15) — Doubleheader-Limits
# ====================================================================

def _dh_days_by_home(season: Season) -> Dict[tuple, int]:
    """(date, home) → max doubleheader_seq (>0 ⇒ Doubleheader an diesem Tag/Ort)."""
    out: Dict[tuple, int] = {}
    for g in season.games:
        if g.doubleheader_seq > 0:
            k = (g.date, g.home)
            out[k] = max(out.get(k, 0), g.doubleheader_seq)
    return out


def check_doubleheader_limits(
    season: Season,
    team_ids: Optional[List[str]] = None,
    *,
    start_min: Optional[Dict[int, int]] = None,
    twi_night_first_min: int = 16 * 60,
    max_twi_night_per_club: int = 3,
) -> List[StructuralViolation]:
    """V(C)(14)/(15)-Doubleheader-Limits (Originalplan).

    - **V(C)(14):** keine Doubleheader an **Folgetagen** (pro Club, Heim oder Auswärts).
    - **V(C)(15):** Twi-Night-DH **≤3 je Heimclub** und **nicht am Getaway-Tag**.
      Twi-Night wird über die Startzeit des ersten DH-Spiels klassifiziert
      (≥ ``twi_night_first_min``) — nur prüfbar, wenn ``start_min`` vorliegt (sonst
      wird der Twi-Night-Teil übersprungen).

    - **V(C)(14) Satz 2:** „The original schedule may contain one home split
      doubleheader for each Club" — geprüft über den seit Review-Runde 2
      (Punkt 1) im Loader erhaltenen ``Game.dh_type`` („S"=split, „Y"=trad.).
      DATENGRENZE (ehrlich): Der SA-Optimierer rekonstruiert Spiele ohne
      ``dh_type`` (``_entries_to_season``) — auf SA-Output ist dieser Teilcheck
      daher leer/vakuos; er greift auf realen Plänen (Loader), Repair- und
      What-if-Outputs (Kopien erhalten den Typ). Auf as-played-Daten sind
      Split-DHs überwiegend Rainout-Makeups → informativ, nicht hart.
    """
    if team_ids is None:
        team_ids = sorted({g.home for g in season.games} | {g.away for g in season.games})
    dh_home = _dh_days_by_home(season)
    viols: List[StructuralViolation] = []

    # V(C)(14): keine DH an Folgetagen je Club
    for t in team_ids:
        # DH-Tage, an denen t beteiligt ist (Heim oder Auswärts)
        t_dh_dates = sorted({g.date for g in season.games_for_team(t)
                             if g.doubleheader_seq > 0})
        for a, b in zip(t_dh_dates, t_dh_dates[1:]):
            if (b - a).days == 1:
                viols.append(StructuralViolation(
                    "V(C)(14)", t, f"Doubleheader an Folgetagen {a} & {b}"))

    # V(C)(14) Satz 2: max. 1 Home-SPLIT-Doubleheader je Club (Review-Runde 2,
    # Punkt 1 — vorher als "nicht prüfbar" dokumentiert, weil der Loader den
    # doubleHeader-Typ wegwarf; jetzt via Game.dh_type prüfbar).
    split_days: Dict[str, set] = {}
    for g in season.games:
        if g.dh_type == "S":
            split_days.setdefault(g.home, set()).add(g.date)
    for home in sorted(split_days):
        days = split_days[home]
        if len(days) > 1:
            viols.append(StructuralViolation(
                "V(C)(14)", home,
                f"{len(days)} Home-Split-Doubleheader (Limit 1 im Originalplan): "
                f"{', '.join(str(d) for d in sorted(days))}"))

    # V(C)(15): Twi-Night-DH ≤3/Heimclub + nicht am Getaway-Tag
    if start_min is not None:
        from .start_times import find_getaway_contexts, AppendixC
        try:
            ac = AppendixC.load()
            getaway_keys = set(find_getaway_contexts(season, ac).keys())
        except Exception:
            getaway_keys = set()
        twi_count: Dict[str, int] = {}
        # erstes DH-Spiel je (date,home) → Startzeit
        first_game = {}
        for g in season.games:
            if g.doubleheader_seq == 1:
                first_game[(g.date, g.home)] = g
        for (d, home), seq in dh_home.items():
            fg = first_game.get((d, home))
            if fg is None:
                continue
            s = start_min.get(fg.game_pk)
            if s is None or s < twi_night_first_min:
                continue  # Day-DH, kein Twi-Night
            twi_count[home] = twi_count.get(home, 0) + 1
            if (d, home) in getaway_keys:
                viols.append(StructuralViolation(
                    "V(C)(15)", home, f"Twi-Night-DH am Getaway-Tag {d}"))
        for home, c in twi_count.items():
            if c > max_twi_night_per_club:
                viols.append(StructuralViolation(
                    "V(C)(15)", home,
                    f"{c} Twi-Night-DH (Limit {max_twi_night_per_club}/Heimclub)"))
    return viols


def original_schedule_violations(
    season: Season,
    team_ids: Optional[List[str]] = None,
    *,
    start_min: Optional[Dict[int, int]] = None,
) -> List[StructuralViolation]:
    """Kombinierter harter Guard für **saubere Original-/Optimierer-Pläne**:
    V(C)(13) + V(C)(14)/(15). Auf as-played-Daten NICHT als hart verwenden
    (Makeup-Artefakte). Genutzt von der Post-Output-Property-Validierung."""
    return (check_offday_distribution(season, team_ids)
            + check_doubleheader_limits(season, team_ids, start_min=start_min))
