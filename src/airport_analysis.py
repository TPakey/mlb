"""Flughafen- vs. Stadt-Koordinaten — Reisemodell-Verfeinerung (P2-4).

Das Produktionsmodell misst Reisedistanzen Großkreis **Stadtzentrum ↔
Stadtzentrum** (`data/teams.json`), validiert auf ~1 % gegen publizierte
MLB-Meilen. Eine optionale Verfeinerung ist, stattdessen den **primären
Metro-Flughafen** je Team zu verwenden (`data/team_airports.json`) — näher am
tatsächlichen Abflugort.

Dieses Modul ist ein **Analyse-Layer**: es berechnet die Saison-Reise unter
Flughafen-Koordinaten und vergleicht sie mit dem Stadt-Modell **und** den
publizierten MLB-Meilen-Ankern (SEA, PIT). Es **verändert das
Produktionsmodell nicht** — Default bleibt Stadt (kein Determinismus-Bruch).
Auf Basis der Messung kann ein Umstieg als dokumentierte Entscheidung erfolgen.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .data_loader import Team
from .season import Season
from .travel import compute_season_travel

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

MILES_TO_KM = 1.609344

# Publizierte MLB-2024-Reisemeilen (Anker; Quelle: docs/PROJECT_REVIEW_2026-06.md).
PUBLISHED_MILES_2024: Dict[str, int] = {"SEA": 47441, "PIT": 26411}


def load_team_airports(path: Optional[Path] = None) -> Dict[str, dict]:
    path = path or (DATA_DIR / "team_airports.json")
    return json.loads(Path(path).read_text(encoding="utf-8"))["airports"]


def teams_with_airport_coords(teams: List[Team],
                              airports: Optional[Dict[str, dict]] = None) -> List[Team]:
    """Kopie der Teamliste mit lat/lon auf die Flughafen-Koordinaten gesetzt."""
    airports = airports or load_team_airports()
    out: List[Team] = []
    for t in teams:
        ap = airports.get(t.id)
        out.append(replace(t, lat=ap["lat"], lon=ap["lon"]) if ap else t)
    return out


@dataclass(frozen=True)
class AirportComparison:
    city_total_km: float
    airport_total_km: float
    per_team_city_km: Dict[str, float]
    per_team_airport_km: Dict[str, float]
    # Anker-Vergleich gegen publizierte Meilen: tid -> (published_km, city_km, airport_km)
    anchors: Dict[str, Tuple[float, float, float]]

    @property
    def delta_pct(self) -> float:
        if not self.city_total_km:
            return 0.0
        return 100.0 * (self.airport_total_km - self.city_total_km) / self.city_total_km

    def anchor_errors(self) -> Dict[str, Tuple[float, float]]:
        """tid -> (city_err_pct, airport_err_pct) gegen publizierte Meilen."""
        out = {}
        for tid, (pub, city, ap) in self.anchors.items():
            out[tid] = (100.0 * (city - pub) / pub, 100.0 * (ap - pub) / pub)
        return out

    def summary(self) -> Dict[str, float]:
        ae = self.anchor_errors()
        return {
            "city_total_km": round(self.city_total_km),
            "airport_total_km": round(self.airport_total_km),
            "delta_pct": round(self.delta_pct, 2),
            "anchor_city_abs_err_pct": round(
                sum(abs(c) for c, _ in ae.values()) / max(1, len(ae)), 2),
            "anchor_airport_abs_err_pct": round(
                sum(abs(a) for _, a in ae.values()) / max(1, len(ae)), 2),
        }


def compare_airport_vs_city(season: Season, teams: List[Team]) -> AirportComparison:
    """Vergleicht Saison-Reise unter Stadt- vs. Flughafen-Koordinaten.

    Anker: publizierte MLB-2024-Meilen für SEA/PIT — zeigt, welches Koordinaten-
    modell die Realität besser trifft.
    """
    city_travel = compute_season_travel(season, teams)
    ap_teams = teams_with_airport_coords(teams)
    ap_travel = compute_season_travel(season, ap_teams)

    per_city = {tid: log.total_km for tid, log in city_travel.by_team.items()}
    per_ap = {tid: log.total_km for tid, log in ap_travel.by_team.items()}

    anchors: Dict[str, Tuple[float, float, float]] = {}
    for tid, miles in PUBLISHED_MILES_2024.items():
        if tid in per_city and tid in per_ap:
            anchors[tid] = (miles * MILES_TO_KM, per_city[tid], per_ap[tid])

    return AirportComparison(
        city_total_km=city_travel.total_km,
        airport_total_km=ap_travel.total_km,
        per_team_city_km=per_city,
        per_team_airport_km=per_ap,
        anchors=anchors,
    )
