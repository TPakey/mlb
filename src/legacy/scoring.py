"""Multi-Dimensionales Scoring-System.

Aus dem Forschungspapier: der Optimizer braucht NICHT einen einzigen Score,
sondern eine Reihe spezialisierter Scores, die später über ein Tradeoff-Profil
kombiniert werden.

Kategorien:
- TravelBurden        — km, Stunden, Zeitzonen-Hops, Ostkurs-Übernachter
- Fatigue             — Reisedichte, lange Auswärtstrips, Backstage-Stress
- Recovery            — Off-Day-Qualität, Ankunftszeiten
- Fairness            — Varianz zwischen Teams in Travel, Rest, TV
- BroadcastValue      — Wert der Matchups in den verfügbaren Slots
- Revenue             — projizierte Attendance/Streaming
- Resilience          — Flexibilität bei Ausfällen

Jeder Score gibt ein dict mit Detail-Komponenten zurück + einen aggregierten
"score"-Wert. Penalties sind so kalibriert, dass sie in der gleichen
Grössenordnung wie km liegen, damit das Tradeoff-Profil-Mixing sinnvoll wirkt.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Tuple

from ..data_loader import Team
from ..distance import TravelLeg
from .schedule_generator import Schedule
from . import penalties as P


# ---------------------- Datentypen ----------------------

@dataclass
class CategoryScore:
    category: str
    score: float                       # Aggregierter Wert (km-Equivalent)
    components: Dict[str, float] = field(default_factory=dict)
    penalty_hits: Dict[str, int] = field(default_factory=dict)

    def add_penalty(self, code: str, count: int = 1) -> None:
        p = P.get(code)
        self.score += p.base * count
        self.penalty_hits[code] = self.penalty_hits.get(code, 0) + count


@dataclass
class ScoreBundle:
    travel: CategoryScore
    fatigue: CategoryScore
    recovery: CategoryScore
    fairness: CategoryScore
    broadcast: CategoryScore
    revenue: CategoryScore
    weather: CategoryScore
    resilience: CategoryScore

    def as_dict(self) -> dict:
        return {k: asdict(v) for k, v in self.__dict__.items()}


# ---------------------- Hilfsfunktionen ----------------------

def _team_route(team_id: str, sched: Schedule) -> List[str]:
    route = [team_id]
    for s in sorted(sched.for_team(team_id), key=lambda x: x.slot):
        if s.home != route[-1]:
            route.append(s.home)
    if route[-1] != team_id:
        route.append(team_id)
    return route


def _team_km(team_id: str, sched: Schedule, leg_map: Dict[Tuple[str, str], TravelLeg]) -> float:
    return sum(leg_map[(a, b)].km for a, b in zip(_team_route(team_id, sched),
                                                   _team_route(team_id, sched)[1:]))


# ---------------------- Score-Berechnungen ----------------------

def score_travel(sched: Schedule, teams: List[Team],
                 leg_map: Dict[Tuple[str, str], TravelLeg]) -> CategoryScore:
    s = CategoryScore(category="travel", score=0.0)
    total_km = 0.0
    total_hours = 0.0
    total_tz = 0
    east_overnight = 0
    for t in teams:
        route = _team_route(t.id, sched)
        prev_lon = None
        for a, b in zip(route, route[1:]):
            leg = leg_map[(a, b)]
            total_km += leg.km
            total_hours += leg.total_hours
            total_tz += leg.timezone_hops
            # Ostkurs-Übernachter: prüfe, ob wir von Westen nach Osten reisen
            # und Distanz > 2000 km (Indikator für coast-to-coast)
            if leg.timezone_hops >= 2 and leg.km > 2000:
                east_overnight += 1
    s.components["total_km"] = total_km
    s.components["total_hours"] = total_hours
    s.components["timezone_hops"] = total_tz
    s.components["east_overnight"] = east_overnight
    s.score = total_km
    if east_overnight > 0:
        s.add_penalty("TRV_EAST_OVERNIGHT", east_overnight)
    return s


def score_fatigue(sched: Schedule, teams: List[Team],
                  leg_map: Dict[Tuple[str, str], TravelLeg]) -> CategoryScore:
    s = CategoryScore(category="fatigue", score=0.0)
    long_road_trips = 0
    rapid_tz_clusters = 0
    for t in teams:
        ts = sorted(sched.for_team(t.id), key=lambda x: x.slot)
        # Lange Auswärtstrips zählen
        away_run = 0
        max_away = 0
        for s_ser in ts:
            if not s_ser.is_home_for(t.id):
                away_run += 1
                max_away = max(max_away, away_run)
            else:
                away_run = 0
        if max_away >= 4:
            long_road_trips += 1
        # Rasche Zeitzonen-Cluster: 4 Hops innerhalb 8 Tage / 2 Slots
        route = _team_route(t.id, sched)
        for i in range(len(route) - 2):
            hops = leg_map[(route[i], route[i + 1])].timezone_hops + \
                   leg_map[(route[i + 1], route[i + 2])].timezone_hops
            if hops >= 4:
                rapid_tz_clusters += 1
                break
    s.components["teams_with_long_road"] = long_road_trips
    s.components["rapid_tz_clusters"] = rapid_tz_clusters
    if long_road_trips:
        s.add_penalty("FAT_LATE_ARRIVAL_RUN", long_road_trips)
    if rapid_tz_clusters:
        s.add_penalty("TRV_FOURTH_TZ_8DAYS", rapid_tz_clusters)
    return s


def score_recovery(sched: Schedule, teams: List[Team],
                   leg_map: Dict[Tuple[str, str], TravelLeg]) -> CategoryScore:
    """Proxy: durchschnittliche Reisestunden pro Slot — weniger = mehr Recovery."""
    s = CategoryScore(category="recovery", score=0.0)
    hours_per_team = []
    for t in teams:
        route = _team_route(t.id, sched)
        h = sum(leg_map[(a, b)].total_hours for a, b in zip(route, route[1:]))
        hours_per_team.append(h)
    avg = statistics.mean(hours_per_team) if hours_per_team else 0
    s.components["avg_travel_hours"] = avg
    s.score = avg * 10.0   # 10x-Faktor, damit Skala vergleichbar zu km
    return s


def score_fairness(sched: Schedule, teams: List[Team],
                   leg_map: Dict[Tuple[str, str], TravelLeg]) -> CategoryScore:
    """Varianz zwischen Teams in km, Heim/Auswärts-Anteil, TZ-Hops."""
    s = CategoryScore(category="fairness", score=0.0)
    kms = [_team_km(t.id, sched, leg_map) for t in teams]
    home_counts = {t.id: 0 for t in teams}
    for ser in sched.series:
        home_counts[ser.home] += 1
    home_vals = list(home_counts.values())
    km_stdev = statistics.pstdev(kms) if len(kms) > 1 else 0
    home_stdev = statistics.pstdev(home_vals) if len(home_vals) > 1 else 0
    s.components["km_stdev"] = km_stdev
    s.components["home_balance_stdev"] = home_stdev
    s.score = km_stdev + home_stdev * 200.0
    if home_stdev > 1.5:
        s.add_penalty("FAIR_REST_DELTA_4PLUS", 1)
    return s


def score_broadcast(sched: Schedule, teams: List[Team],
                    soft_factors: dict) -> CategoryScore:
    """Wertet, wie gut Premier-Matchups in wertvollen Slots liegen."""
    s = CategoryScore(category="broadcast", score=0.0)
    pt = {}
    for entry in soft_factors.get("tv_primetime_matchups", []):
        a, b = entry["teams"]
        w = int(entry["weight"])
        pt[(a, b)] = w
        pt[(b, a)] = w
    hidden_rivalries = 0
    primetime_value = 0.0
    for ser in sched.series:
        w = pt.get((ser.home, ser.away), 0)
        if w <= 0:
            continue
        # "Wochenend-Slot" = ungerader Slot-Index (Heuristik)
        if ser.slot % 2 == 1:
            primetime_value += w * 100
        else:
            hidden_rivalries += 1
    s.components["primetime_value"] = primetime_value
    s.components["hidden_rivalries"] = hidden_rivalries
    # Score = Strafen (hidden) minus Bonus (primetime)
    s.score = -primetime_value
    if hidden_rivalries:
        s.add_penalty("BCAST_RIVALRY_HIDDEN", hidden_rivalries)
    return s


def score_revenue(sched: Schedule, teams: List[Team],
                  teams_by_id: Dict[str, Team]) -> CategoryScore:
    """Heuristik: Wochenend-Heimspiele in Top-Märkten geben Revenue-Punkte."""
    s = CategoryScore(category="revenue", score=0.0)
    top_markets = {"NYY", "NYM", "LAD", "BOS", "CHC", "PHI", "SFG", "ATL", "STL", "HOU"}
    weekend_high = 0
    weekend_low = 0
    for ser in sched.series:
        if ser.slot % 2 != 1:
            continue
        if ser.home in top_markets and ser.away in top_markets:
            weekend_high += 1
        elif ser.home in top_markets and ser.away not in top_markets:
            weekend_low += 1
    s.components["weekend_top_matchups"] = weekend_high
    s.components["weekend_mid_matchups"] = weekend_low
    # Score = Strafen (verschwendete Wochenenden)
    s.score = 0.0
    if weekend_low > 8:
        s.add_penalty("REV_WEEKEND_LOW_DEMAND", weekend_low - 8)
    return s


def score_weather(sched: Schedule, teams: List[Team],
                  teams_by_id: Dict[str, Team], soft_factors: dict) -> CategoryScore:
    s = CategoryScore(category="weather", score=0.0)
    hot_cities = set(soft_factors["weather_profiles"]["hot_july_cities_open_roof"])
    cold_cities = set(soft_factors["weather_profiles"]["cold_april_cities"])

    cold_violations = 0
    hot_violations = 0
    hurricane_hits = 0

    # Slot 0-1 = Anfang April, 14-17 = Juli, 22-26 = Aug/Sep
    for ser in sched.series:
        home = teams_by_id[ser.home]
        if ser.slot <= 1 and home.id in cold_cities and home.roof == "open":
            cold_violations += 1
        if 14 <= ser.slot <= 17 and home.id in hot_cities:
            hot_violations += 1
        if 20 <= ser.slot <= 26 and home.id in {"MIA", "TBR", "HOU"}:
            hurricane_hits += 1

    s.components["cold_april_open"] = cold_violations
    s.components["hot_july_open"] = hot_violations
    s.components["hurricane_window"] = hurricane_hits
    if cold_violations:
        s.add_penalty("WX_COLD_OPEN_APRIL", cold_violations)
    if hot_violations:
        s.add_penalty("WX_HEAT_DAY_GAME", hot_violations)
    if hurricane_hits:
        s.add_penalty("WX_HURRICANE_WINDOW", hurricane_hits)
    return s


def score_resilience(sched: Schedule, teams: List[Team]) -> CategoryScore:
    """Resilienz: Wie viele 'Reserve-Slots' gibt es im Plan?

    Da unser Modell genau 1 Serie pro Slot pro Team annimmt, gibt es keine
    expliziten Off-Slots. Wir messen Resilience proxy-mässig über die
    Verteilung der Reise-Belastung: gleichmässigere Verteilung = leichter
    nachholbar.
    """
    s = CategoryScore(category="resilience", score=0.0)
    away_runs = []
    for t in teams:
        ts = sorted(sched.for_team(t.id), key=lambda x: x.slot)
        run = 0
        max_run = 0
        for ser in ts:
            if not ser.is_home_for(t.id):
                run += 1
                max_run = max(max_run, run)
            else:
                run = 0
        away_runs.append(max_run)
    max_long = max(away_runs) if away_runs else 0
    s.components["worst_away_streak"] = max_long
    if max_long >= 6:
        s.add_penalty("RES_NO_REPAIR_PATH", max_long - 5)
    return s


# ---------------------- Aggregator ----------------------

def compute_scores(sched: Schedule, teams: List[Team],
                   teams_by_id: Dict[str, Team],
                   leg_map: Dict[Tuple[str, str], TravelLeg],
                   soft_factors: dict) -> ScoreBundle:
    return ScoreBundle(
        travel=score_travel(sched, teams, leg_map),
        fatigue=score_fatigue(sched, teams, leg_map),
        recovery=score_recovery(sched, teams, leg_map),
        fairness=score_fairness(sched, teams, leg_map),
        broadcast=score_broadcast(sched, teams, soft_factors),
        revenue=score_revenue(sched, teams, teams_by_id),
        weather=score_weather(sched, teams, teams_by_id, soft_factors),
        resilience=score_resilience(sched, teams),
    )


def weighted_cost(bundle: ScoreBundle, profile) -> float:
    """Kombiniert alle Scores via Tradeoff-Profil zu einem Gesamtkostenwert."""
    return (
        profile.w_travel * bundle.travel.score +
        profile.w_fatigue * bundle.fatigue.score +
        profile.w_fairness * bundle.fairness.score +
        profile.w_broadcast * bundle.broadcast.score +
        profile.w_revenue * bundle.revenue.score +
        profile.w_weather * bundle.weather.score +
        profile.w_resilience * bundle.resilience.score
        # recovery wird nicht doppelt gewichtet (overlaps mit fatigue)
    )
