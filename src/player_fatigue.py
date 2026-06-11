"""Player-Fatigue-Score und CBA-naehe Constraints (AC-2.1.8 / AC-2.1.9).

Zwei zusammenhaengende Funktionen:

1. Validierung harter Constraints
   - max_consecutive_away_days(): "days away from home" gemaess CBA-Definition,
     nie ueber 13. Off-Days *innerhalb* einer Road-Trip zaehlen mit (siehe
     docs/CBA_DEFINITIONS.md).
   - max_games_without_off_day(): nie ueber 20 Spiele ohne Off-Day

2. Soft-Score "Player-Fatigue" pro Plan
   - kumulierte Auswaerts-Sequenzen-Laenge
   - Anzahl back-to-back-Spiele nach Reise
   - Reise-km pro Team (linkt mit `travel.py`, hier nur abstrakt)

Dient als Eingabe fuer das Score-Bundle in `disruption_types.ScoreBundle`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

from .season import Season


# ====================================================================
# Hard-Constraint-Checks (AC-2.1.8 / AC-2.1.9)
# ====================================================================

def max_consecutive_away_days(season: Season, team_id: str) -> int:
    """Laengste Road-Trip eines Teams in "days away from home" (CBA AC-2.1.8).

    Definition gemaess MLB-CBA (siehe docs/CBA_DEFINITIONS.md):
    Eine Road-Trip ist ein zusammenhaengender Block, in dem das Team nicht zu
    Hause ist. Sie beginnt mit dem ersten Auswaertsspiel und endet mit dem
    letzten Auswaertsspiel, bevor das naechste Heimspiel das Team zurueck nach
    Hause bringt. **Off-Days mitten in der Reise zaehlen mit**, weil das Team
    auch dann auswaerts (im Hotel / auf Achse) ist.

    Gemessen wird die Spanne in Kalendertagen vom ersten bis zum letzten
    Auswaertsspiel der Road-Trip (inklusive), also
    ``(last_away_date - first_away_date).days + 1``.

    Beispiel (BOS, BOS, Off, BAL, BAL) -> 5 Tage away from home.
    Ein Heimspiel zwischen zwei Auswaertsspielen beendet die Road-Trip.
    """
    games = sorted([g for g in season.games if g.involves(team_id)],
                    key=lambda g: g.date)
    if not games:
        return 0

    max_trip = 0
    trip_start: Optional[date] = None
    trip_end: Optional[date] = None
    for g in games:
        is_away = (g.away == team_id)
        if is_away:
            if trip_start is None:
                trip_start = g.date
            trip_end = g.date
        else:
            # Heimspiel -> aktuelle Road-Trip endet und wird gewertet
            if trip_start is not None:
                trip_len = (trip_end - trip_start).days + 1
                if trip_len > max_trip:
                    max_trip = trip_len
                trip_start = None
                trip_end = None
    # offene Road-Trip am Saisonende werten
    if trip_start is not None:
        trip_len = (trip_end - trip_start).days + 1
        if trip_len > max_trip:
            max_trip = trip_len
    return max_trip


def max_games_without_off_day(season: Season, team_id: str) -> int:
    """Laengste Folge konsekutiver SPIELTAGE ohne Off-Day fuer ein Team (AC-2.1.9).

    Gemaess MLB-CBA (siehe docs/CBA_DEFINITIONS.md) zaehlt ein **Doubleheader
    als EIN Spieltag** — gemessen werden Kalender-Spieltage, nicht Einzelspiele.
    Ein Off-Day (Tag ohne Spiel) unterbricht die Folge.

    Konsistent mit `generator_optimizer._team_max_streaks._max_run`, das
    ebenfalls distinkte Spieltage zaehlt. (Frueher zaehlte diese Funktion
    Einzelspiele, sodass ein Doubleheader die Folge um 2 erhoehte — das
    widersprach der CBA-Definition und divergierte vom Optimierer.)
    """
    games = [g for g in season.games if g.involves(team_id)]
    if not games:
        return 0

    # Distinkte Spieltage (Doubleheader = 1 Tag); Off-Day = Tag ohne Spiel.
    play_days = sorted({g.date for g in games})

    max_streak = 0
    cur_streak = 0
    prev_day: Optional[date] = None
    for d in play_days:
        if prev_day is not None and (d - prev_day).days == 1:
            cur_streak += 1
        else:
            cur_streak = 1
        prev_day = d
        if cur_streak > max_streak:
            max_streak = cur_streak
    return max_streak


def all_teams_pass_fatigue_constraints(
    season: Season,
    teams: List[str],
    max_consecutive_away: int = 13,
    max_games_no_off_day: int = 20,
) -> Tuple[bool, List[str]]:
    """Prueft AC-2.1.8 und AC-2.1.9 fuer alle gegebenen Teams.

    Liefert (alle_ok, liste_von_violations_messages).
    """
    violations: List[str] = []
    for tid in teams:
        c = max_consecutive_away_days(season, tid)
        if c > max_consecutive_away:
            violations.append(
                f"AC-2.1.8 violated: {tid} hat {c} konsekutive Auswaerts-Tage "
                f"(Limit {max_consecutive_away})"
            )
        n = max_games_without_off_day(season, tid)
        if n > max_games_no_off_day:
            violations.append(
                f"AC-2.1.9 violated: {tid} hat {n} Spiele ohne Off-Day "
                f"(Limit {max_games_no_off_day})"
            )
    return (not violations, violations)


# ====================================================================
# Fatigue-Score (fuer Score-Bundle)
# ====================================================================

@dataclass(frozen=True)
class FatigueReport:
    by_team_max_consec_away: Dict[str, int]
    by_team_max_no_off: Dict[str, int]
    league_total_fatigue: float

    @property
    def worst_consec_away(self) -> int:
        return max(self.by_team_max_consec_away.values()) if self.by_team_max_consec_away else 0

    @property
    def worst_no_off_day(self) -> int:
        return max(self.by_team_max_no_off.values()) if self.by_team_max_no_off else 0


def compute_fatigue_report(season: Season, team_ids: List[str]) -> FatigueReport:
    """Berechnet einen Fatigue-Report pro Team und einen aggregierten Score.

    Aggregat-Score (heuristisch):
      league_total_fatigue = sum(max_consec_away_per_team^2)
                            + 0.5 * sum(max_no_off_day_per_team^2)
    Quadrierte Strafterm-Form gibt grossen Streaks stark mehr Gewicht.
    """
    consec = {t: max_consecutive_away_days(season, t) for t in team_ids}
    no_off = {t: max_games_without_off_day(season, t) for t in team_ids}
    score = sum(v * v for v in consec.values()) + 0.5 * sum(v * v for v in no_off.values())
    return FatigueReport(
        by_team_max_consec_away=consec,
        by_team_max_no_off=no_off,
        league_total_fatigue=float(score),
    )
