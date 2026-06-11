"""Strategie C: Venue-Swap mit Revanche.

Statt Spiele zeitlich zu verschieben (A, B), tauscht diese Strategie das
Heimrecht zwischen einem Disruption-Spiel und einem spaeteren Counterpart-
Spiel zwischen denselben Teams. Damit:

- Disruption-Spiel wird zu Away-Spiel am Counterpart-Stadion → faellt
  ausserhalb des betroffenen Stadions
- Counterpart wird zu Heim-Spiel im urspruenglichen Heimstadion (was
  ausserhalb der Disruption liegt)
- Heim/Auswaerts-Bilanz pro Team bleibt unveraendert
- Daten bleiben gleich

Begrenzung:
- Funktioniert NUR, wenn ein Counterpart-Spiel (gleiche Teams, Heimrecht
  umgekehrt, nicht selbst betroffen) existiert.
- Bei Milton (TBR alle Heimspiele gesperrt) finden wir keinen TBR-Counterpart
  fuer die meisten Spiele — Strategie C ist dort partiell.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple, Union

from .disruption_types import (
    StadiumBlackout, WeatherWindow, MassPostponement,
    GameChange,
)
from .repair_local import affected_games
from .season import Game, Season


DisruptionInput = Union[StadiumBlackout, WeatherWindow, MassPostponement]


def repair_venue_swap(
    season: Season,
    disruption: DisruptionInput,
    teams_city_lookup: Optional[Dict[str, str]] = None,
) -> Tuple[Season, List[GameChange], List[Game]]:
    """Strategie C — Venue-Swap mit Revanche.

    Liefert (new_season, changes, unresolvable).

    `unresolvable` enthaelt Disruption-Spiele, fuer die kein Counterpart
    gefunden wurde.
    """
    affected = affected_games(season, disruption, teams_city_lookup)
    affected_pks: Set[int] = {g.game_pk for g in affected}

    # Pro Team-Pair (home, away): Liste der affected-Spiele
    affected_by_pair: Dict[Tuple[str, str], List[Game]] = defaultdict(list)
    for g in affected:
        affected_by_pair[(g.home, g.away)].append(g)

    # Counterpart-Index: Spiele mit umgekehrtem Heimrecht, NICHT selbst betroffen
    counterparts: Dict[Tuple[str, str], List[Game]] = defaultdict(list)
    for g in season.games:
        if g.game_pk in affected_pks:
            continue
        counterparts[(g.away, g.home)].append(g)   # Schluessel: orig-(home, away)

    # Sortiere Counterparts deterministisch nach Datum
    for k in counterparts:
        counterparts[k].sort(key=lambda x: (x.date, x.game_pk))

    # Plan: pro Affected-Spiel das naechste freie Counterpart waehlen
    swap_pairs: List[Tuple[Game, Game]] = []
    unresolvable: List[Game] = []
    used_counterpart_pks: Set[int] = set()

    for pair, aff_list in affected_by_pair.items():
        aff_list_sorted = sorted(aff_list, key=lambda g: (g.date, g.game_pk))
        cp_candidates = [
            g for g in counterparts.get(pair, [])
            if g.game_pk not in used_counterpart_pks
        ]
        if len(cp_candidates) < len(aff_list_sorted):
            # Nicht genug Counterparts — Rest in unresolvable
            for i, ag in enumerate(aff_list_sorted):
                if i < len(cp_candidates):
                    swap_pairs.append((ag, cp_candidates[i]))
                    used_counterpart_pks.add(cp_candidates[i].game_pk)
                else:
                    unresolvable.append(ag)
        else:
            for i, ag in enumerate(aff_list_sorted):
                swap_pairs.append((ag, cp_candidates[i]))
                used_counterpart_pks.add(cp_candidates[i].game_pk)

    # Build new_games mit den Swaps angewendet
    swap_target_pks = {sp[0].game_pk: sp[1] for sp in swap_pairs}   # affected -> counterpart
    swap_source_pks = {sp[1].game_pk: sp[0] for sp in swap_pairs}   # counterpart -> affected
    new_games: List[Game] = []
    changes: List[GameChange] = []

    for g in season.games:
        if g.game_pk in swap_target_pks:
            # Heim-Auswaerts tauschen, Datum bleibt
            new_g = Game(
                game_pk=g.game_pk,
                date=g.date,
                home=g.away,             # Tausch
                away=g.home,             # Tausch
                venue=g.away,            # neues Heimstadion
                doubleheader_seq=g.doubleheader_seq,
                game_type=g.game_type,
                dh_type=g.dh_type,
            )
            new_games.append(new_g)
            changes.append(GameChange(
                original_game_pk=g.game_pk,
                change_type="swap",
                new_date=g.date,
                new_home=g.away,
                new_away=g.home,
                note=f"Venue-Swap: Heimrecht von {g.home} an {g.away}; Revanche-Counterpart pk={swap_target_pks[g.game_pk].game_pk}",
            ))
        elif g.game_pk in swap_source_pks:
            new_g = Game(
                game_pk=g.game_pk,
                date=g.date,
                home=g.away,
                away=g.home,
                venue=g.away,
                doubleheader_seq=g.doubleheader_seq,
                game_type=g.game_type,
                dh_type=g.dh_type,
            )
            new_games.append(new_g)
            changes.append(GameChange(
                original_game_pk=g.game_pk,
                change_type="swap",
                new_date=g.date,
                new_home=g.away,
                new_away=g.home,
                note=f"Revanche-Swap: Heimrecht von {g.home} an {g.away}; ersetzt urspruengliches Disruption-Spiel pk={swap_source_pks[g.game_pk].game_pk}",
            ))
        else:
            new_games.append(g)

    new_games.sort(key=lambda g: (g.date, g.game_pk))
    new_season = Season(
        season=season.season,
        games=new_games,
        season_start=season.season_start,
        season_end=season.season_end,
        all_star_dates=season.all_star_dates,
    )
    return new_season, changes, unresolvable
