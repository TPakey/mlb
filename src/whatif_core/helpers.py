"""What-if Helfer (A21-Split): Delta-Bau, Slot-Suche, Spiel-Verschiebung.

Privatfunktionen + DIMENSION_LABELS. Re-exportiert ueber `src.whatif`.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional, Set, Tuple

from ..pareto_types import ParetoBundle
from ..season import Game, Season
from .types import DimensionDelta


DIMENSION_LABELS: Dict[str, Tuple[str, str, bool]] = {
    # key: (anzeigename, einheit, minimize)
    "travel_km":            ("Reisedistanz",      "km",    True),
    "revenue_usd":          ("Gate-Revenue",       "USD",   False),
    "fatigue_score":        ("Fatigue-Score",      "pts",   True),
    "max_away_streak":      ("Max Away-Streak",    "Tage",  True),
    "off_day_variance":     ("Off-Day-Varianz",    "",      True),
    "tv_slot_score":        ("TV-Score",           "pts",   False),
    "event_friction":       ("Event-Friction",     "pts",   True),
    "constraint_violations":("Constraint-Viols.",  "",      True),
}


def _flag_publish_gate(original: Season, modified: Season,
                       warnings: List[str]) -> None:
    """Review-Fix P0-1 (2026-06-10): Publish-Gate auch hinter dem What-if-Output.

    Misst den modifizierten Plan mit dem projekteigenen Compliance-Tooling
    (Baseline = Ausgangsplan, d. h. geerbte as-played-Artefakte zaehlen nicht).
    What-if ist explorativ → Verstoss wird als laute Warnung im Ergebnis
    MARKIERT (nicht verworfen), damit kein Szenario-Plan unbemerkt als
    publizierbar durchgeht. Deterministisch, reine Messung."""
    try:
        from ..publish_gate import publishable_report
        gate = publishable_report(modified, baseline=original)
        if not gate.is_publishable:
            warnings.append(f"PUBLISH-GATE: {gate.summary()}")
    except Exception as exc:  # pragma: no cover — Gate darf What-if nie crashen
        warnings.append(f"PUBLISH-GATE: Messung fehlgeschlagen ({exc})")


def _flag_constraint_violations(mod_bundle, warnings: List[str],
                                 feasible: bool) -> bool:
    """Post-Whatif-Validator (2.10.5): meldet harte Constraint-Verletzungen.

    Prüft das modifizierte ParetoBundle auf `constraint_violations > 0`
    (AC-2.1.8/9) und legt eine Warnung in `warnings` ab. Gibt das ggf. auf
    False gesetzte `feasible`-Flag zurück.
    """
    viol = getattr(mod_bundle, "constraint_violations", 0)
    if viol and viol > 0:
        warnings.append(
            f"Modifizierter Plan verletzt {int(viol)} harte Constraint(s) "
            f"(AC-2.1.8/9) — Plan ist nicht feasibel."
        )
        return False
    return feasible


def _build_deltas(orig: ParetoBundle, mod: ParetoBundle) -> List[DimensionDelta]:
    """Berechnet die Deltas aller 8 Dimensionen."""
    deltas: List[DimensionDelta] = []
    for name, (label, unit, minimize) in DIMENSION_LABELS.items():
        o = float(getattr(orig, name))
        m = float(getattr(mod, name))
        delta = m - o
        delta_pct = (delta / o * 100) if o != 0 else 0.0

        # Richtung: "better" wenn Verbesserung in Optimierungsrichtung
        eps = 1e-6
        if abs(delta) < eps:
            direction = "neutral"
        elif minimize:
            direction = "better" if delta < 0 else "worse"
        else:
            direction = "better" if delta > 0 else "worse"

        deltas.append(DimensionDelta(
            name=name, label=label, unit=unit,
            original=o, modified=m,
            delta=delta, delta_pct=delta_pct,
            direction=direction, minimize=minimize,
        ))
    return deltas


# ====================================================================
# Interne Hilfsfunktionen für Serien-Reparatur
# ====================================================================

def _occupied_days(season: Season, team_id: str) -> Set[date]:
    """Alle Spieltage eines Teams in der Saison."""
    return {g.date for g in season.games if g.involves(team_id)}


def _find_series_for_matchup(
    season: Season, home: str, away: str
) -> List[List[Game]]:
    """Findet alle Serien (= zusammenhängende Spielblöcke) zwischen home@away."""
    games = sorted(
        [g for g in season.games if g.home == home and g.away == away],
        key=lambda g: g.date,
    )
    if not games:
        return []
    groups: List[List[Game]] = []
    cur = [games[0]]
    for g in games[1:]:
        if (g.date - cur[-1].date).days <= 1:
            cur.append(g)
        else:
            groups.append(cur)
            cur = [g]
    groups.append(cur)
    return groups


def _find_free_slot(
    season: Season,
    teams: List[str],
    series_length: int,
    preferred_start: date,
    search_forward: bool = True,
    blackout: Optional[Set[date]] = None,
    season_start: Optional[date] = None,
    season_end: Optional[date] = None,
) -> Optional[date]:
    """Sucht den nächsten freien Starttermin für eine Serie der gegebenen Länge.

    "Frei" = keines der angegebenen Teams hat in [start, start+length-1] ein Spiel,
    und kein Tag fällt in das Blackout-Set.

    Sucht zuerst vorwärts, dann rückwärts (sofern search_forward=True).
    """
    blackout = blackout or set()
    s_start = season_start or date(preferred_start.year, 3, 1)
    s_end = season_end or date(preferred_start.year, 10, 31)
    # M4 (Sprint 2.10): All-Star-Break ist tabu — kein verschobenes Spiel darf
    # in den Break fallen.
    asb_dates: Set[date] = set(season.all_star_dates or ())

    occupied: Dict[str, Set[date]] = {
        tid: _occupied_days(season, tid) for tid in teams
    }

    def _is_free(start: date) -> bool:
        if start < s_start or start + timedelta(days=series_length - 1) > s_end:
            return False
        for off in range(series_length):
            d = start + timedelta(days=off)
            if d in blackout or d in asb_dates:
                return False
            for tid in teams:
                if d in occupied[tid]:
                    return False
        return True

    # Vorwärts suchen
    max_search = (s_end - s_start).days
    for delta in range(0, max_search):
        candidate = preferred_start + timedelta(days=delta)
        if _is_free(candidate):
            return candidate

    # Rückwärts suchen (als Fallback)
    for delta in range(1, max_search):
        candidate = preferred_start - timedelta(days=delta)
        if _is_free(candidate):
            return candidate

    return None


def _move_games_to_date(games: List[Game], new_start: date, pk_offset: int = 0) -> List[Game]:
    """Verschiebt eine Gruppe von Spielen auf ein neues Startdatum.

    Spiele werden konsekutiv ab new_start platziert (Spielabstand je 1 Tag).
    Doubleheader (gleicher Ausgangstag) bleiben auf demselben neuen Tag.
    """
    if not games:
        return []
    old_start = games[0].date
    result: List[Game] = []
    for g in games:
        day_offset = (g.date - old_start).days
        new_date = new_start + timedelta(days=day_offset)
        result.append(Game(
            game_pk=g.game_pk + pk_offset,
            date=new_date,
            home=g.home,
            away=g.away,
            venue=g.venue,
            doubleheader_seq=g.doubleheader_seq,
            game_type=g.game_type,
                dh_type=g.dh_type,
        ))
    return result


def _replace_games(season: Season, old_games: List[Game], new_games: List[Game]) -> Season:
    """Ersetzt eine Menge von Spielen durch neue Spiele in einer Saison."""
    old_pks = {g.game_pk for g in old_games}
    remaining = [g for g in season.games if g.game_pk not in old_pks]
    all_games = sorted(remaining + new_games, key=lambda g: (g.date, g.game_pk))
    return Season(
        season=season.season,
        games=all_games,
        season_start=season.season_start,
        season_end=season.season_end,
        all_star_dates=season.all_star_dates,
    )


