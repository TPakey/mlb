"""Strategie B: Constrained Re-Generate.

Nimmt die Original-Saison als Vorlage, extrahiert die Matchup-Quoten und
generiert komplett neu — diesmal mit einer zusaetzlichen Constraint, die
das Disruption-Fenster fuer das betroffene Heim-Team blockiert.

Im Gegensatz zu Strategie A (Local Repair) wird der gesamte Plan neu
gerechnet. Vorteile:
- findet ein globales km-/Verteilungs-Optimum unter der Disruption-Constraint
- ist gut, wenn die Disruption lang ist (mehrere Heim-Serien)
Nachteile:
- viele Spiele aendern sich (hohe change_pct)
- braucht ~17 s (volle Sprint-2.1-Pipeline)
- kann INFEASIBLE werden, wenn die Disruption-Lage zu wenig Restplaetze laesst
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, FrozenSet, List, Set, Tuple, Union

from .disruption_types import (
    StadiumBlackout, WeatherWindow, MassPostponement,
    GameChange,
)
from .generator import GeneratorConfig, GeneratorResult, generate
from .matchup_extractor import extract_matchup_quotas
from .season import Game, Season


DisruptionInput = Union[StadiumBlackout, WeatherWindow, MassPostponement]


def _disruption_to_blackout_days(
    disruption: DisruptionInput,
    season_start: date,
    teams_city_lookup: Dict[str, str],
) -> Dict[str, FrozenSet[int]]:
    """Konvertiert eine Disruption in die Generator-Eingabe `home_blackout_days`.

    Liefert ein Dict team_id -> frozen set der Tag-Indizes (relativ zu
    season_start), an denen das Team keine Heimspiele haben darf.
    """
    out: Dict[str, Set[int]] = {}
    if isinstance(disruption, StadiumBlackout):
        days = set()
        d = disruption.start_date
        while d <= disruption.end_date:
            days.add((d - season_start).days)
            d += timedelta(days=1)
        out[disruption.home_team] = days
    elif isinstance(disruption, WeatherWindow):
        # Alle Teams in dieser Stadt finden
        affected_teams = [
            tid for tid, city in teams_city_lookup.items()
            if city == disruption.city
        ]
        if not affected_teams:
            return {}
        days = set()
        d = disruption.start_date
        while d <= disruption.end_date:
            days.add((d - season_start).days)
            d += timedelta(days=1)
        for tid in affected_teams:
            out[tid] = days
    elif isinstance(disruption, MassPostponement):
        # Mass-Postponement betrifft konkrete Spiele, nicht Tage — Strategie B
        # ignoriert diese Sorte Disruption (wir koennen die Tage der
        # betroffenen Spiele blockieren, aber das ist eine Nicht-Operation,
        # weil die Spiele nach Re-Generate ohnehin neu plaziert werden).
        return {}
    return {tid: frozenset(days) for tid, days in out.items()}


def repair_regenerate(
    season: Season,
    disruption: DisruptionInput,
    cfg_template: GeneratorConfig,
    teams_city_lookup: Dict[str, str],
) -> Tuple[Season, List[GameChange], GeneratorResult]:
    """Strategie B — Constrained Re-Generate.

    Liefert (new_season, changes, generator_result).

    `changes` ist hier eine vereinfachte Liste: weil der Plan komplett neu
    gerechnet wird, sind im Allgemeinen die meisten Spiele "different".
    Wir liefern aber eine konkrete Diff-Liste pro Spiel (game_pk → neues Datum
    bzw. "rebuilt"-Marker), damit nachgelagerte Tools (Report-Renderer, UI)
    saubere Daten haben.
    """
    blackout = _disruption_to_blackout_days(
        disruption, cfg_template.season_start, teams_city_lookup
    )

    # Neue GeneratorConfig — gleicher Seed, gleiche Saison, plus Blackout
    cfg = GeneratorConfig(
        season=cfg_template.season,
        season_start=cfg_template.season_start,
        season_end=cfg_template.season_end,
        all_star_break=cfg_template.all_star_break,
        max_solver_time_seconds=cfg_template.max_solver_time_seconds,
        num_search_workers=cfg_template.num_search_workers,
        random_seed=cfg_template.random_seed,
        log_search_progress=cfg_template.log_search_progress,
        enable_travel_optimization=cfg_template.enable_travel_optimization,
        travel_optimizer_iterations=cfg_template.travel_optimizer_iterations,
        travel_optimizer_shift_max_days=cfg_template.travel_optimizer_shift_max_days,
        travel_optimizer_start_temperature=cfg_template.travel_optimizer_start_temperature,
        travel_optimizer_end_temperature=cfg_template.travel_optimizer_end_temperature,
        teams_path=cfg_template.teams_path,
        home_blackout_days=blackout,
    )

    quotas = extract_matchup_quotas(season)
    result = generate(quotas, cfg)

    if result.season is None:
        return season, [], result

    # Diff bauen: paarweise key by (home, away) — wir matchen Originalspiele
    # an neue Spiele und vergleichen Daten.
    changes = _compute_changes(season, result.season)
    return result.season, changes, result


def _compute_changes(original: Season, new: Season) -> List[GameChange]:
    """Vergleich von Original- und neuem Plan auf Spiel-Ebene.

    Wir matchen Spiele paarweise per (home, away) — wenn ein Matchup mehrfach
    vorkommt, ordnen wir die Spiele chronologisch zu. Aenderungen werden als
    'move' (selber Matchup, neues Datum) erfasst.
    """
    from collections import defaultdict
    orig_by_pair: Dict[Tuple[str, str], List[Game]] = defaultdict(list)
    new_by_pair: Dict[Tuple[str, str], List[Game]] = defaultdict(list)
    for g in original.games:
        orig_by_pair[(g.home, g.away)].append(g)
    for g in new.games:
        new_by_pair[(g.home, g.away)].append(g)
    for k in orig_by_pair:
        orig_by_pair[k].sort(key=lambda g: g.date)
    for k in new_by_pair:
        new_by_pair[k].sort(key=lambda g: g.date)

    changes: List[GameChange] = []
    for pair, og_list in orig_by_pair.items():
        ng_list = new_by_pair.get(pair, [])
        for i, og in enumerate(og_list):
            if i < len(ng_list):
                ng = ng_list[i]
                if ng.date != og.date:
                    changes.append(GameChange(
                        original_game_pk=og.game_pk,
                        change_type="move",
                        new_date=ng.date,
                        note=f"Re-generate: {og.date} -> {ng.date}",
                    ))
            else:
                changes.append(GameChange(
                    original_game_pk=og.game_pk,
                    change_type="cancel",
                    note="Spiel im neuen Plan nicht enthalten",
                ))
    return changes
