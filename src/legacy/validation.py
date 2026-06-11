"""Validation Harness — vergleicht echten MLB-Spielplan mit optimaler Routenfuehrung.

Methodik (Sprint 1):
====================
Wir optimieren NICHT die Matchups, sondern *nur* die Reihenfolge der
besuchten Staedte innerhalb einer Road Trip. Eine Road Trip ist eine
zusammenhaengende Folge von Auswaertsspielen ohne Zwischenstopp daheim.

Fuer jede Road Trip loesen wir das TSP exakt (Permutations-Enumeration,
typischerweise 2-5 Staedte) und vergleichen:
- ORIGINAL: die tatsaechliche Reihenfolge laut MLB-Stats-API
- OPTIMAL:  die TSP-optimale Reihenfolge

Das Delta ist eine **Upper-Bound-Einsparung**. Echte koordinierte
Optimierung erreicht davon einen Teil, weil die Heim-Termine der jeweils
anderen Teams ebenfalls passen muessen. Aber: die Zahl ist mathematisch
sauber und auf echten Daten gemessen.

Output:
- pro Team: Anzahl Trips, Original-km, Optimale-km, Einsparung
- pro Trip: groesste Einsparpotentiale
- pro Saison: Gesamteinsparung, Verteilung, CO2- und USD-Aequivalent
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import permutations
from typing import Dict, List, Tuple

from ..data_loader import Team
from ..distance import haversine_km
from .metrics import CO2_KG_PER_KM, COST_USD_PER_KM
from ..season import GameSeries, Season


@dataclass
class RoadTrip:
    """Eine zusammenhaengende Folge von Auswaerts-Serien ohne Heim-Aufenthalt."""
    team_id: str
    series: Tuple[GameSeries, ...]
    cities: Tuple[str, ...]              # Heim-Team-IDs der besuchten Staedte
    nights: int                          # Tage zwischen Trip-Start und -Ende

    @property
    def num_cities(self) -> int:
        return len(self.cities)


@dataclass
class TripValidationResult:
    trip_idx: int                       # 0-basierter Index innerhalb des Teams
    team_id: str
    cities_original: Tuple[str, ...]
    cities_optimal: Tuple[str, ...]
    km_original: float
    km_optimal: float
    savings_km: float
    savings_pct: float
    nights: int

    @property
    def changed(self) -> bool:
        return self.cities_original != self.cities_optimal


@dataclass
class TeamValidationResult:
    team_id: str
    num_road_trips: int
    num_optimizable_trips: int           # Trips mit >=2 Staedten
    trips: List[TripValidationResult] = field(default_factory=list)

    @property
    def total_km_original(self) -> float:
        return sum(t.km_original for t in self.trips)

    @property
    def total_km_optimal(self) -> float:
        return sum(t.km_optimal for t in self.trips)

    @property
    def total_savings_km(self) -> float:
        return self.total_km_original - self.total_km_optimal

    @property
    def savings_pct(self) -> float:
        if self.total_km_original < 1e-9:
            return 0.0
        return self.total_savings_km / self.total_km_original * 100

    @property
    def num_trips_changed(self) -> int:
        return sum(1 for t in self.trips if t.changed)


@dataclass
class SeasonValidationResult:
    season: int
    by_team: Dict[str, TeamValidationResult] = field(default_factory=dict)
    methodology: str = "intra-trip TSP (upper-bound)"

    @property
    def total_km_original(self) -> float:
        return sum(r.total_km_original for r in self.by_team.values())

    @property
    def total_km_optimal(self) -> float:
        return sum(r.total_km_optimal for r in self.by_team.values())

    @property
    def total_savings_km(self) -> float:
        return self.total_km_original - self.total_km_optimal

    @property
    def savings_pct(self) -> float:
        if self.total_km_original < 1e-9:
            return 0.0
        return self.total_savings_km / self.total_km_original * 100

    @property
    def total_co2_savings_kg(self) -> float:
        return self.total_savings_km * CO2_KG_PER_KM

    @property
    def total_cost_savings_usd(self) -> float:
        return self.total_savings_km * COST_USD_PER_KM

    def top_improving_trips(self, n: int = 10) -> List[TripValidationResult]:
        all_trips = [t for r in self.by_team.values() for t in r.trips]
        return sorted(all_trips, key=lambda t: -t.savings_km)[:n]


# ---------------------- Helper Functions ----------------------

def identify_road_trips(team_id: str, season: Season) -> List[RoadTrip]:
    """Gruppiert konsekutive Auswaertsserien zu Road Trips."""
    series_list = season.series_for_team(team_id)
    trips: List[RoadTrip] = []
    current: List[GameSeries] = []
    for s in series_list:
        if s.is_home_for(team_id):
            if current:
                trips.append(_build_trip(team_id, current))
                current = []
        else:
            current.append(s)
    if current:
        trips.append(_build_trip(team_id, current))
    return trips


def _build_trip(team_id: str, series_list: List[GameSeries]) -> RoadTrip:
    cities = tuple(s.home for s in series_list)
    nights = (series_list[-1].end_date - series_list[0].start_date).days
    return RoadTrip(
        team_id=team_id,
        series=tuple(series_list),
        cities=cities,
        nights=nights,
    )


def compute_trip_km(home_team: Team, city_order: Tuple[str, ...],
                    teams_by_id: Dict[str, Team]) -> float:
    """Summiert km fuer eine Trip-Reihenfolge: Home -> city1 -> ... -> cityN -> Home."""
    if not city_order:
        return 0.0
    path = [home_team.id] + list(city_order) + [home_team.id]
    total = 0.0
    for a, b in zip(path, path[1:]):
        ta, tb = teams_by_id[a], teams_by_id[b]
        if ta.id == tb.id:
            continue
        total += haversine_km(ta.lat, ta.lon, tb.lat, tb.lon)
    return total


def optimize_trip_order(home_team: Team, cities: Tuple[str, ...],
                        teams_by_id: Dict[str, Team]) -> Tuple[Tuple[str, ...], float]:
    """Findet die km-optimale Reihenfolge fuer eine Road Trip (exaktes TSP).

    Returns (optimale_reihenfolge, optimale_km). Bei nur einer Stadt ist die
    Reihenfolge eindeutig.
    """
    if len(cities) <= 1:
        return cities, compute_trip_km(home_team, cities, teams_by_id)

    if len(cities) > 8:
        # Sicherheitsvorbehalt: fuer >8 Staedte exponentiell aufwaendig.
        # In der Praxis hat ein MLB-Trip selten >5 Staedte.
        return cities, compute_trip_km(home_team, cities, teams_by_id)

    best_order = cities
    best_km = compute_trip_km(home_team, cities, teams_by_id)
    for perm in permutations(cities):
        km = compute_trip_km(home_team, perm, teams_by_id)
        if km < best_km - 1e-9:
            best_km = km
            best_order = perm
    return best_order, best_km


# ---------------------- Main API ----------------------

def validate_team(team: Team, season: Season,
                  teams_by_id: Dict[str, Team]) -> TeamValidationResult:
    trips = identify_road_trips(team.id, season)
    result = TeamValidationResult(
        team_id=team.id,
        num_road_trips=len(trips),
        num_optimizable_trips=sum(1 for t in trips if t.num_cities >= 2),
    )
    for idx, trip in enumerate(trips):
        original_order = trip.cities
        original_km = compute_trip_km(team, original_order, teams_by_id)
        optimal_order, optimal_km = optimize_trip_order(team, original_order, teams_by_id)
        savings_km = original_km - optimal_km
        savings_pct = (savings_km / original_km * 100) if original_km > 1e-9 else 0.0
        result.trips.append(TripValidationResult(
            trip_idx=idx,
            team_id=team.id,
            cities_original=original_order,
            cities_optimal=optimal_order,
            km_original=original_km,
            km_optimal=optimal_km,
            savings_km=savings_km,
            savings_pct=savings_pct,
            nights=trip.nights,
        ))
    return result


def validate_season(season: Season,
                    teams: List[Team]) -> SeasonValidationResult:
    teams_by_id = {t.id: t for t in teams}
    result = SeasonValidationResult(season=season.season)
    for team in teams:
        result.by_team[team.id] = validate_team(team, season, teams_by_id)
    return result


# ---------------------- Reporting ----------------------

def format_summary(result: SeasonValidationResult) -> str:
    """Markdown-Zusammenfassung fuer den Sprint-Review."""
    lines = []
    lines.append(f"# Validation Report - MLB Season {result.season}")
    lines.append("")
    lines.append(f"**Methodik:** {result.methodology}")
    lines.append("")
    lines.append("## Zusammenfassung")
    lines.append("")
    lines.append(f"- **Original-Reisedistanz** (alle 30 Teams): {result.total_km_original:,.0f} km")
    lines.append(f"- **Optimale Trip-Routenfuehrung**: {result.total_km_optimal:,.0f} km")
    lines.append(f"- **Theoretische Einsparung**: {result.total_savings_km:,.0f} km "
                 f"({result.savings_pct:.2f} %)")
    lines.append(f"- **CO2-Einsparung**: {result.total_co2_savings_kg / 1000:,.1f} t")
    lines.append(f"- **Kosten-Einsparung**: ${result.total_cost_savings_usd / 1e6:,.2f} M")
    lines.append("")
    lines.append("> **Interpretation:** Dies ist eine **Upper-Bound-Einsparung**.")
    lines.append("> Wir nehmen den Matchup-Kalender als gegeben und optimieren nur die ")
    lines.append("> Reihenfolge der Stadt-Besuche innerhalb jeder Road Trip exakt per TSP. ")
    lines.append("> Echte koordinierte Liga-Optimierung muesste auch die Termine der ")
    lines.append("> jeweils anderen Teams beruecksichtigen und erreicht davon einen Teil.")
    lines.append("")
    lines.append("## Pro Team")
    lines.append("")
    lines.append("| Team | Trips | Optimierbar | Veraenderte | Original km | Optimal km | Einsparung | % |")
    lines.append("|------|------:|------------:|------------:|------------:|-----------:|-----------:|---:|")
    sorted_teams = sorted(result.by_team.values(), key=lambda r: -r.total_savings_km)
    for tr in sorted_teams:
        lines.append(
            f"| {tr.team_id} | {tr.num_road_trips} | {tr.num_optimizable_trips} | "
            f"{tr.num_trips_changed} | {tr.total_km_original:,.0f} | "
            f"{tr.total_km_optimal:,.0f} | {tr.total_savings_km:,.0f} | "
            f"{tr.savings_pct:.2f} |"
        )
    lines.append("")
    lines.append("## Top 10 Trips mit hoechstem Einsparpotential")
    lines.append("")
    lines.append("| Team | Naechte | Original-Route | Optimal-Route | km Original | km Optimal | Einsparung |")
    lines.append("|------|--------:|----------------|---------------|------------:|-----------:|-----------:|")
    for t in result.top_improving_trips(10):
        orig = " -> ".join(t.cities_original)
        opt = " -> ".join(t.cities_optimal)
        lines.append(
            f"| {t.team_id} | {t.nights} | {orig} | {opt} | "
            f"{t.km_original:,.0f} | {t.km_optimal:,.0f} | {t.savings_km:,.0f} |"
        )
    return "\n".join(lines)


def result_to_dict(result: SeasonValidationResult) -> dict:
    """Serialisierbare Form fuer Dashboard und Persistenz."""
    return {
        "season": result.season,
        "methodology": result.methodology,
        "totals": {
            "km_original": result.total_km_original,
            "km_optimal": result.total_km_optimal,
            "savings_km": result.total_savings_km,
            "savings_pct": result.savings_pct,
            "co2_savings_kg": result.total_co2_savings_kg,
            "cost_savings_usd": result.total_cost_savings_usd,
        },
        "by_team": {
            tid: {
                "team_id": tr.team_id,
                "num_road_trips": tr.num_road_trips,
                "num_optimizable_trips": tr.num_optimizable_trips,
                "num_trips_changed": tr.num_trips_changed,
                "total_km_original": tr.total_km_original,
                "total_km_optimal": tr.total_km_optimal,
                "total_savings_km": tr.total_savings_km,
                "savings_pct": tr.savings_pct,
                "trips": [
                    {
                        "trip_idx": t.trip_idx,
                        "cities_original": list(t.cities_original),
                        "cities_optimal": list(t.cities_optimal),
                        "km_original": t.km_original,
                        "km_optimal": t.km_optimal,
                        "savings_km": t.savings_km,
                        "savings_pct": t.savings_pct,
                        "nights": t.nights,
                        "changed": t.changed,
                    }
                    for t in tr.trips
                ],
            }
            for tid, tr in result.by_team.items()
        },
    }
