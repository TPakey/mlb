"""Kennzahlen für den Vergleich Original vs. optimierter Spielplan."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple

from ..data_loader import Team
from ..distance import TravelLeg
from .schedule_generator import Schedule

# CO2-Faktor für Charterjets (Boeing 737-800 Klasse): ~110 g CO2 pro Passagier-km,
# Charterflug typisch ~50 Passagiere → wir rechnen pro Flug (nicht pro Passagier):
# ~5.5 kg CO2 pro km für die ganze Mannschaftsmaschine.
CO2_KG_PER_KM = 5.5

# Charter-Kosten (Schätzwert): ~ 30 USD pro km für eine Mannschaftsmaschine,
# inkl. Crew, Treibstoff, Gebühren. Stark vereinfacht.
COST_USD_PER_KM = 30.0


@dataclass
class TeamMetrics:
    team_id: str
    total_km: float
    total_hours: float
    timezone_hops: int
    cross_country_trips: int      # Flüge > 3000 km
    longest_trip_km: float
    co2_kg: float
    cost_usd: float


@dataclass
class ScheduleMetrics:
    by_team: Dict[str, TeamMetrics]
    total_km: float
    total_co2_kg: float
    total_cost_usd: float
    total_hours: float
    soft_penalty: float


def _team_route(team_id: str, schedule: Schedule) -> List[str]:
    """Reise-Sequenz für ein Team über die Saison.

    Beim Auswärtsspiel reist das Team in die Heim-Stadt des Gegners.
    Beim Heimspiel ist es im eigenen Stadion.
    Vor der Saison und nach Auswärts-Trips startet/endet das Team daheim.
    """
    route = [team_id]  # Saisonstart: zuhause
    for s in sorted(schedule.for_team(team_id), key=lambda x: x.slot):
        venue = s.home  # Standort der Serie ist immer das Heim-Team
        if venue != route[-1]:
            route.append(venue)
    if route[-1] != team_id:
        route.append(team_id)
    return route


def compute_metrics(
    schedule: Schedule,
    teams: List[Team],
    leg_map: Dict[Tuple[str, str], TravelLeg],
    soft_penalty: float = 0.0,
) -> ScheduleMetrics:
    by_team: Dict[str, TeamMetrics] = {}
    for t in teams:
        route = _team_route(t.id, schedule)
        km = 0.0
        hours = 0.0
        tz = 0
        cross = 0
        longest = 0.0
        for a, b in zip(route, route[1:]):
            leg = leg_map[(a, b)]
            km += leg.km
            hours += leg.total_hours
            tz += leg.timezone_hops
            if leg.km > 3000:
                cross += 1
            longest = max(longest, leg.km)
        by_team[t.id] = TeamMetrics(
            team_id=t.id,
            total_km=km,
            total_hours=hours,
            timezone_hops=tz,
            cross_country_trips=cross,
            longest_trip_km=longest,
            co2_kg=km * CO2_KG_PER_KM,
            cost_usd=km * COST_USD_PER_KM,
        )
    total_km = sum(m.total_km for m in by_team.values())
    return ScheduleMetrics(
        by_team=by_team,
        total_km=total_km,
        total_co2_kg=total_km * CO2_KG_PER_KM,
        total_cost_usd=total_km * COST_USD_PER_KM,
        total_hours=sum(m.total_hours for m in by_team.values()),
        soft_penalty=soft_penalty,
    )


def metrics_to_dict(m: ScheduleMetrics) -> dict:
    return {
        "by_team": {tid: asdict(tm) for tid, tm in m.by_team.items()},
        "total_km": m.total_km,
        "total_co2_kg": m.total_co2_kg,
        "total_cost_usd": m.total_cost_usd,
        "total_hours": m.total_hours,
        "soft_penalty": m.soft_penalty,
    }
