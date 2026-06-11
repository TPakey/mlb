"""analyze_team_impact + TeamImpact (A21-Split). Re-exportiert ueber `src.whatif`."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ..data_loader import Team
from ..season import Season


@dataclass(frozen=True)
class TeamImpact:
    """Impact-Analyse für ein einzelnes Team."""
    team_id: str
    travel_delta_km: float
    games_added: int
    games_removed: int
    home_games_delta: int
    away_games_delta: int
    affected_series: List[str]   # menschenlesbare Beschreibung


def analyze_team_impact(
    original: Season,
    modified: Season,
    team_id: str,
    teams: Optional[List[Team]] = None,
) -> TeamImpact:
    """Analysiert den Einfluss einer Modifikation auf ein einzelnes Team.

    Nützlich nach whatif_force_series oder whatif_blackout, um zu sehen
    welche Teams am stärksten betroffen sind.

    Args:
        original:  Originaler Saisonplan.
        modified:  Modifizierter Saisonplan.
        team_id:   Team-ID (z.B. "NYY").
        teams:     Alle 30 Teams. Wenn angegeben (N6, Sprint 2.10), wird das
                   Travel-Delta exakt über `compute_team_travel` berechnet statt
                   über den groben 500-km-pro-Standortwechsel-Proxy.

    Returns:
        TeamImpact mit Deltas für dieses Team.
    """
    orig_games = set(g.game_pk for g in original.games if g.involves(team_id))
    mod_games = set(g.game_pk for g in modified.games if g.involves(team_id))

    added_pks = mod_games - orig_games
    removed_pks = orig_games - mod_games

    def _count_home(season: Season, tid: str) -> int:
        return sum(1 for g in season.games if g.home == tid)

    def _count_away(season: Season, tid: str) -> int:
        return sum(1 for g in season.games if g.away == tid)

    home_delta = _count_home(modified, team_id) - _count_home(original, team_id)
    away_delta = _count_away(modified, team_id) - _count_away(original, team_id)

    # Betroffene Serien beschreiben
    affected_desc: List[str] = []
    for g in sorted(modified.games, key=lambda g: g.date):
        if g.game_pk in added_pks:
            role = "Heim" if g.home == team_id else "Auswärts"
            opp = g.away if g.home == team_id else g.home
            affected_desc.append(f"+{g.date} vs {opp} ({role})")
    for g in sorted(original.games, key=lambda g: g.date):
        if g.game_pk in removed_pks:
            role = "Heim" if g.home == team_id else "Auswärts"
            opp = g.away if g.home == team_id else g.home
            affected_desc.append(f"-{g.date} vs {opp} ({role})")

    # Travel-Delta (N6, Sprint 2.10): exakt via compute_team_travel, falls die
    # Team-Objekte vorliegen; sonst grober 500-km-pro-Standortwechsel-Proxy.
    if teams is not None:
        from ..travel import compute_team_travel
        teams_by_id = {t.id: t for t in teams}
        team_obj = teams_by_id.get(team_id)
        if team_obj is not None:
            km_orig = compute_team_travel(team_obj, original, teams_by_id).total_km
            km_mod = compute_team_travel(team_obj, modified, teams_by_id).total_km
            travel_delta = km_mod - km_orig
        else:
            travel_delta = 0.0
    else:
        # Fallback-Proxy: ~500 km pro Standortwechsel (Liga-Durchschnitt)
        def _location_changes(season: Season, tid: str) -> int:
            gs = sorted(season.games_for_team(tid), key=lambda g: g.date)
            changes = 0
            prev_venue = None
            for g in gs:
                venue = g.home
                if prev_venue is not None and venue != prev_venue:
                    changes += 1
                prev_venue = venue
            return changes

        lc_orig = _location_changes(original, team_id)
        lc_mod = _location_changes(modified, team_id)
        travel_delta = (lc_mod - lc_orig) * 500.0

    return TeamImpact(
        team_id=team_id,
        travel_delta_km=travel_delta,
        games_added=len(added_pks),
        games_removed=len(removed_pks),
        home_games_delta=home_delta,
        away_games_delta=away_delta,
        affected_series=affected_desc[:20],   # max 20 für Report-Übersicht
    )
