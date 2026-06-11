"""Trip-Dossier-Generator (Scheduler-Ops).

Bindet die Ops-Bausteine zu **operativen Dossiers je Auswärts-Stadt** eines
Teams zusammen: Boden-Routing (Flughafen↔Hotel↔Stadion), Hotel-Empfehlung
(inkl. Buchungshistorie) und City-Security-/Risiko-Briefing — abgeleitet aus dem
optimierten Saisonplan. Das ist die Brücke vom *Kalender* (was die Optimierung
liefert) zum *tatsächlichen Reisebetrieb* (was Travel-/Security-Ops braucht).

Pro Auswärts-Serie eines Teams: Gastgeber-Stadt, Termine, Gegner, empfohlenes
Hotel (Score + Historie), Routing mit stadt-spezifischen Stau-Faktoren und ein
saison-bewusstes Security-Briefing. High-Profile-Kontext (Rivalität/Feiertag)
wird markiert.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from .season import Season
from .data_loader import load_teams, teams_by_id
from .airport_analysis import load_team_airports
from .ops_routing import city_routing, Coord, CityRouting
from .ops_hotels import recommend_hotels, HotelScore
from .ops_security import build_security_briefing, load_ops_profiles, SecurityBriefing


@dataclass(frozen=True)
class CityDossier:
    visiting_team: str
    host_team: str
    city: str
    stadium: str
    start_date: date
    end_date: date
    n_games: int
    routing: CityRouting
    hotel_ranking: List[HotelScore]
    security: SecurityBriefing
    high_profile: List[str] = field(default_factory=list)

    @property
    def recommended_hotel(self) -> Optional[HotelScore]:
        return self.hotel_ranking[0] if self.hotel_ranking else None


def _high_profile_flags(host: str, visitor: str, start: date,
                        marquee_fn=None, holiday_days=None) -> List[str]:
    flags: List[str] = []
    if marquee_fn is not None and marquee_fn(host, visitor) > 1.0:
        flags.append("Marquee-/Rivalitäts-Begegnung (erhöhte Crowd-/Medien-Posture)")
    if holiday_days and start in holiday_days:
        flags.append("Feiertags-Spiel (volle Auslastung, Verkehr/Logistik beachten)")
    return flags


def build_city_dossier(visiting_team: str, host_team: str,
                       start: date, end: date, n_games: int, *,
                       profiles: Optional[Dict] = None,
                       tbi: Optional[Dict] = None,
                       airports: Optional[Dict] = None,
                       marquee_fn=None, holiday_days=None) -> CityDossier:
    profiles = profiles or load_ops_profiles()
    tbi = tbi or teams_by_id(load_teams())
    airports = airports or load_team_airports()
    prof = profiles[host_team]

    # Hotel-Empfehlung (Top-Kandidat liefert Routing-Hotel-Coord)
    hotels = recommend_hotels(host_team, tbi=tbi)
    hotel_coord = None
    if hotels:
        h = hotels[0].hotel
        hotel_coord = Coord(h.name, h.lat, h.lon)

    routing = city_routing(
        host_team, hotel=hotel_coord,
        detour=prof.get("detour", 1.35),
        congestion=prof.get("congestion", 1.4),
        redundancy=prof.get("route_redundancy", 2),
        tbi=tbi, airports=airports,
    )
    security = build_security_briefing(host_team, month=start.month, profiles=profiles)
    flags = _high_profile_flags(host_team, visiting_team, start, marquee_fn, holiday_days)

    return CityDossier(
        visiting_team=visiting_team, host_team=host_team,
        city=prof.get("city", ""), stadium=prof.get("stadium", ""),
        start_date=start, end_date=end, n_games=n_games,
        routing=routing, hotel_ranking=hotels, security=security,
        high_profile=flags,
    )


def team_trip_dossiers(season: Season, team_id: str, *,
                       profiles: Optional[Dict] = None,
                       tbi: Optional[Dict] = None,
                       airports: Optional[Dict] = None,
                       marquee_fn=None, holiday_days=None,
                       limit: Optional[int] = None) -> List[CityDossier]:
    """Dossiers für alle Auswärts-Serien (Stadtbesuche) eines Teams."""
    profiles = profiles or load_ops_profiles()
    tbi = tbi or teams_by_id(load_teams())
    airports = airports or load_team_airports()
    if marquee_fn is None:
        try:
            from .tv_slots import TvSlotConfig
            marquee_fn = TvSlotConfig.load().marquee_mult
        except Exception:
            marquee_fn = None

    out: List[CityDossier] = []
    for s in season.series_for_team(team_id):
        if s.is_home_for(team_id):
            continue                       # nur Auswärts-Serien = Stadtbesuche
        host = s.home
        if host not in profiles:
            continue
        out.append(build_city_dossier(
            team_id, host, s.start_date, s.end_date, s.length,
            profiles=profiles, tbi=tbi, airports=airports,
            marquee_fn=marquee_fn, holiday_days=holiday_days,
        ))
        if limit and len(out) >= limit:
            break
    return out


# ---------------- Markdown-Rendering ----------------

def dossier_to_markdown(d: CityDossier) -> str:
    from .ops_security import briefing_to_markdown
    from .ops_hotels import recommendation_markdown
    L: List[str] = []
    L.append(f"## {d.city} — {d.host_team} ({d.start_date}…{d.end_date}, {d.n_games} Spiele)")
    L.append(f"*Gast: {d.visiting_team}. Stadion: {d.stadium}.*")
    if d.high_profile:
        L.append("")
        L.append("> ⚑ " + " · ".join(d.high_profile))
    L.append("")
    # Routing
    L.append("### Boden-Routing")
    L.append("| Strecke | km (Straße) | Fahrzeit | Planbarkeit |")
    L.append("|---|---:|---:|---:|")
    for leg in (d.routing.airport_to_hotel, d.routing.hotel_to_ballpark,
                d.routing.airport_to_ballpark):
        if leg:
            L.append(f"| {leg.from_name} → {leg.to_name} | {leg.road_km:.1f} | "
                     f"{leg.drive_min:.0f} min | {leg.reliability:.0%} |")
    L.append("")
    # Hotel
    L.append(recommendation_markdown(d.host_team, d.hotel_ranking, city=d.city))
    L.append("")
    # Security
    L.append(briefing_to_markdown(d.security))
    return "\n".join(L)


def team_dossier_report(season: Season, team_id: str,
                        dossiers: Optional[List[CityDossier]] = None) -> str:
    if dossiers is None:
        dossiers = team_trip_dossiers(season, team_id)
    L = [f"# Trip-Operations-Dossier — {team_id} (Saison {season.season})",
         "",
         f"Auswärts-Stadtbesuche: {len(dossiers)}. Pro Stadt: Routing, "
         "Hotel-Empfehlung (inkl. Historie), Security-/Risiko-Briefing.",
         ""]
    # Risiko-Übersicht
    L.append("## Risiko-Übersicht (Auswärts-Städte)")
    L.append("| Stadt | Termine | Risiko | Transfer-Planbarkeit | Hotel |")
    L.append("|---|---|:--:|---:|---|")
    for d in dossiers:
        hotel = d.recommended_hotel.hotel.name if d.recommended_hotel else "—"
        L.append(f"| {d.city} | {d.start_date} | {d.security.risk_level} | "
                 f"{d.routing.airport_to_ballpark.reliability:.0%} | {hotel} |")
    L.append("")
    for d in dossiers:
        L.append(dossier_to_markdown(d))
        L.append("\n---\n")
    return "\n".join(L)
