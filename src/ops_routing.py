"""Ground-Routing-Engine: Flughafen ↔ Hotel ↔ Stadion (Scheduler-Ops).

Der Saison-Optimierer plant *welche* Stadt wann besucht wird. Der eigentliche
Job eines MLB-Travel-Ops-Teams beginnt danach: die **Bodenlogistik** in jeder
besuchten Stadt — vom Flughafen ins Hotel, vom Hotel ins Stadion und zurück,
auf den zuverlässigsten Wegen, mit realistischen Fahrzeiten.

Diese Engine berechnet das **koordinaten-basiert und nachvollziehbar**:
- Luftlinie (Haversine) zwischen Flughafen (`data/team_airports.json`), Stadion
  (`data/teams.json`) und Hotel.
- **Straßendistanz** = Luftlinie × stadt-spezifischer Umwegfaktor (Detour;
  US-Stadtnetze typ. 1,25–1,45×; Default 1,35).
- **Fahrzeit** = Straßendistanz / effektive Geschwindigkeit, wobei die effektive
  Geschwindigkeit aus einer freien Reisegeschwindigkeit und einem stadt-/tageszeit-
  abhängigen **Stau-Faktor** (Congestion 1,0 frei … 2,2 schwer) abgeleitet wird.
- **Zuverlässigkeits-Score** (0–1): sinkt mit der Stau-Varianz und steigt mit
  Routen-Redundanz (mehrere Korridore). Spiegelt die Planungs-Frage „wie viel
  Puffer braucht der Mannschaftsbus?".

Die Heuristiken sind dokumentiert und **stadt-überschreibbar** (das Ops-Profil
liefert Detour/Congestion/Redundanz je Stadt). In Produktion kann der Schätzer
1:1 durch eine Maps-/Routing-API ersetzt werden — die Schnittstelle (`RouteLeg`)
bleibt gleich.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from .distance import haversine_km
from .data_loader import load_teams, teams_by_id
from .airport_analysis import load_team_airports

# ---- Default-Modellparameter (dokumentiert, stadt-überschreibbar) ----
DEFAULT_DETOUR = 1.35              # Straße/Luftlinie (US-Stadtnetz-Mittel)
DEFAULT_FREE_SPEED_KMH = 70.0      # freie Reisegeschwindigkeit Charter-Bus (Highway-Mix)
DEFAULT_CONGESTION = 1.4           # 1.0 frei … 2.2 schwer (Mittel großstädtisch)
DEFAULT_REDUNDANCY = 2            # Anzahl praktikabler Korridore (mehr = robuster)


@dataclass(frozen=True)
class RouteLeg:
    from_name: str
    to_name: str
    crow_km: float
    road_km: float
    drive_min: float
    reliability: float            # 0..1 (1 = sehr planbar)
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "from": self.from_name, "to": self.to_name,
            "crow_km": round(self.crow_km, 1), "road_km": round(self.road_km, 1),
            "drive_min": round(self.drive_min, 1),
            "reliability": round(self.reliability, 2), "note": self.note,
        }


def _reliability(congestion: float, redundancy: int) -> float:
    """Zuverlässigkeit aus Stau-Niveau + Korridor-Redundanz.

    Höherer Stau senkt die Planbarkeit (größere Zeit-Varianz); mehr alternative
    Korridore heben sie wieder an. Auf [0.15, 0.99] geklemmt.
    """
    base = 1.10 - 0.42 * (congestion - 1.0)        # 1.0→1.10, 2.2→0.60
    base += 0.05 * max(0, redundancy - 1)          # je Alternativ-Korridor +0.05
    return max(0.15, min(0.99, base))


def estimate_route(from_name: str, to_name: str,
                   from_lat: float, from_lon: float,
                   to_lat: float, to_lon: float, *,
                   detour: float = DEFAULT_DETOUR,
                   free_speed_kmh: float = DEFAULT_FREE_SPEED_KMH,
                   congestion: float = DEFAULT_CONGESTION,
                   redundancy: int = DEFAULT_REDUNDANCY,
                   note: str = "") -> RouteLeg:
    crow = haversine_km(from_lat, from_lon, to_lat, to_lon)
    road = crow * detour
    eff_speed = free_speed_kmh / max(1.0, congestion)
    drive_min = 60.0 * road / max(1.0, eff_speed)
    return RouteLeg(from_name, to_name, crow, road, drive_min,
                    _reliability(congestion, redundancy), note)


@dataclass(frozen=True)
class Coord:
    name: str
    lat: float
    lon: float


def ballpark_coord(team_id: str, tbi: Optional[Dict] = None) -> Coord:
    tbi = tbi or teams_by_id(load_teams())
    t = tbi[team_id]
    return Coord(f"{t.stadium}", t.lat, t.lon)


def airport_coord(team_id: str, airports: Optional[Dict] = None) -> Coord:
    airports = airports or load_team_airports()
    ap = airports[team_id]
    return Coord(ap["code"], ap["lat"], ap["lon"])


@dataclass(frozen=True)
class CityRouting:
    team_id: str
    airport_to_ballpark: RouteLeg
    airport_to_hotel: Optional[RouteLeg]
    hotel_to_ballpark: Optional[RouteLeg]

    def to_dict(self) -> dict:
        return {
            "team_id": self.team_id,
            "airport_to_ballpark": self.airport_to_ballpark.to_dict(),
            "airport_to_hotel": self.airport_to_hotel.to_dict() if self.airport_to_hotel else None,
            "hotel_to_ballpark": self.hotel_to_ballpark.to_dict() if self.hotel_to_ballpark else None,
        }


def city_routing(team_id: str, *,
                 hotel: Optional[Coord] = None,
                 detour: float = DEFAULT_DETOUR,
                 congestion: float = DEFAULT_CONGESTION,
                 redundancy: int = DEFAULT_REDUNDANCY,
                 free_speed_kmh: float = DEFAULT_FREE_SPEED_KMH,
                 tbi: Optional[Dict] = None,
                 airports: Optional[Dict] = None) -> CityRouting:
    """Vollständiges Boden-Routing für die Gast-Stadt von ``team_id``.

    ``hotel`` optional (Coord); fehlt es, werden nur Flughafen↔Stadion berechnet.
    Stadt-Parameter (detour/congestion/redundancy) kommen in Produktion aus dem
    Ops-Profil (``data/city_ops_profiles.json``).
    """
    bp = ballpark_coord(team_id, tbi)
    ap = airport_coord(team_id, airports)
    kw = dict(detour=detour, congestion=congestion, redundancy=redundancy,
              free_speed_kmh=free_speed_kmh)
    ap_bp = estimate_route(ap.name, bp.name, ap.lat, ap.lon, bp.lat, bp.lon,
                           note="Flughafen → Stadion (Team-Bus)", **kw)
    ap_h = hb = None
    if hotel is not None:
        ap_h = estimate_route(ap.name, hotel.name, ap.lat, ap.lon,
                              hotel.lat, hotel.lon,
                              note="Flughafen → Team-Hotel", **kw)
        hb = estimate_route(hotel.name, bp.name, hotel.lat, hotel.lon,
                            bp.lat, bp.lon,
                            note="Hotel → Stadion (Gameday-Transfer)", **kw)
    return CityRouting(team_id, ap_bp, ap_h, hb)
