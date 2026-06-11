"""Distanz- und Reisezeitmodell für MLB-Teams.

Wir verwenden Haversine für die geografische Distanz und übersetzen das in
realistische Charter-Flugzeiten (inkl. Boden-/Pufferzeit).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

# Audit A15 (Sprint A-3): Timezone-Logik liegt jetzt in einem zykluskontrollierten
# Modul `timezones`, das weder data_loader noch distance importiert.
from .timezones import TIMEZONE_OFFSET, tz_offset_hours  # noqa: F401 — TIMEZONE_OFFSET ist oeffentlicher Re-Export (tests/test_invariants u. a.)  # noqa: F401  (TIMEZONE_OFFSET wird re-exportiert: tests/test_invariants importiert es aus src.distance)
from .data_loader import Team

EARTH_RADIUS_KM = 6371.0

# Charter-Modell: durchschnittliche Reisegeschwindigkeit + fester Overhead.
# - Reise-Cruise ~ 800 km/h, aber inkl. Steigflug/Sinkflug effektiv ~ 700 km/h
# - Bus zum Flughafen, Boarding, Gepäck, Bus zum Hotel: ~ 3 Stunden Overhead
CHARTER_CRUISE_KMH = 700.0
GROUND_OVERHEAD_HOURS = 3.0
TIMEZONE_PENALTY_HOURS_PER_ZONE = 0.5  # Jetlag-Aufschlag pro Zeitzonen-Hop


# Audit A15 (Sprint A-3): `TIMEZONE_OFFSET` und `tz_offset_hours` werden aus
# `src.timezones` re-exportiert (oben importiert) — keine eigene Definition
# mehr in diesem Modul.


@dataclass(frozen=True)
class TravelLeg:
    from_team: str
    to_team: str
    km: float
    flight_hours: float
    total_hours: float
    timezone_hops: int


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Großkreis-Distanz in km."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def travel_leg(from_team: Team, to_team: Team,
               on_date: Optional[date] = None) -> TravelLeg:
    """Reisesegment zwischen zwei Teams.

    `on_date` (Reisedatum) aktiviert DST-korrekte Timezone-Hops (M2). Ohne
    Datum wird der statische Standard-Time-Offset verwendet.
    """
    if from_team.id == to_team.id:
        return TravelLeg(from_team.id, to_team.id, 0.0, 0.0, 0.0, 0)
    km = haversine_km(from_team.lat, from_team.lon, to_team.lat, to_team.lon)
    flight_h = km / CHARTER_CRUISE_KMH
    tz_hops = abs(tz_offset_hours(from_team.timezone, on_date)
                  - tz_offset_hours(to_team.timezone, on_date))
    total_h = flight_h + GROUND_OVERHEAD_HOURS + tz_hops * TIMEZONE_PENALTY_HOURS_PER_ZONE
    return TravelLeg(from_team.id, to_team.id, km, flight_h, total_h, tz_hops)


def distance_matrix(teams: List[Team], on_date: Optional[date] = None
                    ) -> Tuple[Dict[Tuple[str, str], float], Dict[Tuple[str, str], TravelLeg]]:
    """Liefert zwei Strukturen:
    - reines km-Mapping (für KPIs)
    - vollständige Reisesegmente (für Optimierer)

    `on_date` wird an `travel_leg` durchgereicht und aktiviert die DST-korrekten
    Timezone-Hops (M2) für ein konkretes Datum. **Ohne `on_date` ist die Matrix
    bewusst datums-agnostisch** und nutzt die statischen Standard-Time-Offsets —
    die km sind davon unberührt, nur `total_hours`/`timezone_hops` würden sich
    DST-bedingt unterscheiden. Für datumsgenaue Reisezeiten pro Spiel siehe
    `travel.compute_team_travel`, das ohnehin das echte Spieldatum verwendet.
    """
    km_map: Dict[Tuple[str, str], float] = {}
    leg_map: Dict[Tuple[str, str], TravelLeg] = {}
    for a in teams:
        for b in teams:
            leg = travel_leg(a, b, on_date)
            km_map[(a.id, b.id)] = leg.km
            leg_map[(a.id, b.id)] = leg
    return km_map, leg_map


def total_travel(route: List[str], leg_map: Dict[Tuple[str, str], TravelLeg]) -> Tuple[float, float, int]:
    """Summiert eine Reiseroute (Liste von Team-IDs in Reihenfolge der Stops).

    Returns: (km_total, hours_total, tz_hops_total)
    """
    km = 0.0
    hours = 0.0
    tz = 0
    for a, b in zip(route, route[1:]):
        leg = leg_map[(a, b)]
        km += leg.km
        hours += leg.total_hours
        tz += leg.timezone_hops
    return km, hours, tz
