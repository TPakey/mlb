"""Travel-Berechnung auf der Tagesebene (echtes 162-Spiele-Modell).

Berechnet pro Team die Reisedistanz und -zeit über die Saison, basierend auf
der `Season`-Datenstruktur (siehe `season.py`).

Reisemodell:
- Saisonstart und -ende: das Team beginnt und endet daheim
- Vor jedem Heimspiel ist das Team daheim
- Vor jedem Auswärtsspiel ist das Team am Stadion des Gegners
- Reisesegmente entstehen, wenn sich der Standort zwischen aufeinanderfolgenden
  Spielen ändert
- Off-Days zwischen Serien werden als "Travel-Days" interpretiert: das Team
  reist von einem Spiel zum nächsten und hat dazwischen Zeit zur Erholung
- Doubleheader (zwei Spiele am selben Tag, selber Ort) erzeugen keinen
  Reisesegment

Die zurückgegebenen Strukturen entsprechen denen aus `metrics.py`, sodass
das bestehende Scoring und Dashboard sie konsumieren können.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Tuple

from .data_loader import Team
from .distance import (
    CHARTER_CRUISE_KMH,
    GROUND_OVERHEAD_HOURS,
    TIMEZONE_PENALTY_HOURS_PER_ZONE,
    haversine_km,
    tz_offset_hours,
)
from .season import Season


@dataclass(frozen=True)
class TravelSegment:
    """Ein Reisesegment zwischen zwei aufeinanderfolgenden Spiel-Standorten."""
    from_team: str          # Heimteam des Abreise-Stadions
    to_team: str            # Heimteam des Ziel-Stadions
    from_date: date         # Datum des letzten Spiels am Abreiseort
    to_date: date           # Datum des ersten Spiels am Zielort
    km: float
    flight_hours: float
    overhead_hours: float
    timezone_hops: int
    travel_days: int        # Tage zwischen From-Date und To-Date


@dataclass
class TeamTravelLog:
    team_id: str
    segments: List[TravelSegment] = field(default_factory=list)
    games_played: int = 0
    home_games: int = 0
    away_games: int = 0
    off_days: int = 0

    @property
    def total_km(self) -> float:
        return sum(s.km for s in self.segments)

    @property
    def total_flight_hours(self) -> float:
        return sum(s.flight_hours for s in self.segments)

    @property
    def total_overhead_hours(self) -> float:
        return sum(s.overhead_hours for s in self.segments)

    @property
    def total_timezone_hops(self) -> int:
        return sum(s.timezone_hops for s in self.segments)

    @property
    def cross_country_trips(self) -> int:
        return sum(1 for s in self.segments if s.km > 3000)

    @property
    def longest_trip_km(self) -> float:
        return max((s.km for s in self.segments), default=0.0)

    @property
    def num_segments(self) -> int:
        return len(self.segments)


def compute_team_travel(team: Team, season: Season,
                        teams_by_id: Dict[str, Team]) -> TeamTravelLog:
    """Berechnet das Travel-Log für ein Team über eine komplette Saison.

    Konventionen:
    - Saison startet zu Hause: vor dem ersten Spiel ist das Team am Heim-Stadion
      (falls erstes Spiel Heim, dann Distanz 0; falls Auswärts, dann Reise zum Gegner).
    - Saison endet zu Hause: nach dem letzten Spiel reist das Team heim (falls
      letztes Spiel Auswärts).
    """
    games = season.games_for_team(team.id)
    if not games:
        return TeamTravelLog(team_id=team.id)

    log = TeamTravelLog(team_id=team.id)
    log.games_played = len(games)
    log.home_games = sum(1 for g in games if g.home == team.id)
    log.away_games = log.games_played - log.home_games
    log.off_days = len(season.off_days(team.id))

    # Sequenz: Startpunkt + Standorte aller Spiele + Endpunkt (heim)
    venue_sequence: List[Tuple[date, str]] = [(games[0].date, team.id)]
    for g in games:
        venue_sequence.append((g.date, g.home))
    if venue_sequence[-1][1] != team.id:
        # Letztes Spiel war auswärts → Rückreise nach Hause
        venue_sequence.append((games[-1].date + timedelta(days=1), team.id))

    # Segmente bilden, wenn sich der Standort ändert
    prev_date, prev_loc = venue_sequence[0]
    for cur_date, cur_loc in venue_sequence[1:]:
        if cur_loc == prev_loc:
            # Doubleheader oder fortgesetzte Serie — keine Reise
            prev_date, prev_loc = cur_date, cur_loc
            continue
        from_t = teams_by_id[prev_loc]
        to_t = teams_by_id[cur_loc]
        km = haversine_km(from_t.lat, from_t.lon, to_t.lat, to_t.lon)
        flight_h = km / CHARTER_CRUISE_KMH
        # DST-korrekte Timezone-Hops zum konkreten Reisedatum (M2, Sprint 2.11).
        tz_hops = abs(
            tz_offset_hours(from_t.timezone, cur_date)
            - tz_offset_hours(to_t.timezone, cur_date)
        )
        overhead_h = GROUND_OVERHEAD_HOURS + tz_hops * TIMEZONE_PENALTY_HOURS_PER_ZONE
        travel_days = max(0, (cur_date - prev_date).days - 1)
        log.segments.append(TravelSegment(
            from_team=prev_loc,
            to_team=cur_loc,
            from_date=prev_date,
            to_date=cur_date,
            km=km,
            flight_hours=flight_h,
            overhead_hours=overhead_h,
            timezone_hops=tz_hops,
            travel_days=travel_days,
        ))
        prev_date, prev_loc = cur_date, cur_loc

    return log


@dataclass
class SeasonTravelReport:
    season: int
    by_team: Dict[str, TeamTravelLog] = field(default_factory=dict)

    @property
    def total_km(self) -> float:
        return sum(log.total_km for log in self.by_team.values())

    @property
    def avg_km_per_team(self) -> float:
        return self.total_km / max(1, len(self.by_team))

    @property
    def median_km(self) -> float:
        vals = sorted(log.total_km for log in self.by_team.values())
        if not vals:
            return 0.0
        n = len(vals)
        return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2

    @property
    def total_segments(self) -> int:
        return sum(log.num_segments for log in self.by_team.values())

    def summary_table(self) -> str:
        lines = [
            f"{'Team':4s}  {'Spiele':>6s}  {'Reisen':>6s}  {'km':>9s}  {'Flug-h':>7s}  "
            f"{'TZ':>3s}  {'CC':>3s}  {'Longest':>8s}"
        ]
        for tid in sorted(self.by_team.keys(), key=lambda t: -self.by_team[t].total_km):
            log = self.by_team[tid]
            lines.append(
                f"{tid:4s}  {log.games_played:>6d}  {log.num_segments:>6d}  "
                f"{log.total_km:>9,.0f}  {log.total_flight_hours:>7.1f}  "
                f"{log.total_timezone_hops:>3d}  {log.cross_country_trips:>3d}  "
                f"{log.longest_trip_km:>8,.0f}"
            )
        return "\n".join(lines)


def compute_season_travel(season: Season, teams: List[Team]) -> SeasonTravelReport:
    teams_by_id = {t.id: t for t in teams}
    report = SeasonTravelReport(season=season.season)
    for t in teams:
        report.by_team[t.id] = compute_team_travel(t, season, teams_by_id)
    return report
