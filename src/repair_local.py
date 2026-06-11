"""Strategie A: Local Repair — Postpone-to-Next-Off-Day.

Verschiebt nur die direkt durch die Disruption betroffenen Spiele auf den
naechsten Tag, an dem beide Teams frei sind. Der Rest des Plans bleibt
bit-identisch. Garantiert die geringste Plan-Abweichung (AC-2.2.5).

Annahmen:
- Wir verschieben nur in die Zukunft (forward postponement), nicht nach
  vorne — die Disruption ist meist ein in-saison-Ereignis und retroaktive
  Verschiebungen sind operativ nicht moeglich.
- Es wird der naechste Tag gesucht, an dem BEIDE Teams frei sind. Doubleheader
  werden hier NICHT als Fallback erzeugt (QA-Hinweis 2026-05-29: ein frueherer
  Docstring versprach das, der Slot-Finder lehnt aber jeden Tag ab, an dem eines
  der Teams bereits spielt). Wer Doubleheader-Makeups zulassen will, muss den
  Slot-Finder erweitern (und DH-Sequenz-Nummern korrekt setzen).
- Wenn kein Slot gefunden wird, faellt das Spiel auf "unreschedulable"
  und der Caller muss eine andere Strategie waehlen.

Diese Strategie ist die schnellste der drei (typisch < 1 Sekunde fuer
eine einzelne Heim-Serie), aber findet kein globales Optimum.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional, Set, Tuple, Union

from .disruption_types import (
    StadiumBlackout, WeatherWindow, MassPostponement,
    GameChange,
)
from .season import Game, Season


DisruptionInput = Union[StadiumBlackout, WeatherWindow, MassPostponement]


# ====================================================================
# Helper: betroffene Spiele identifizieren
# ====================================================================

def _city_of_team(team_id: str, teams_lookup: Dict[str, str]) -> str:
    """Stadt eines Teams (aus teams_lookup: team_id -> city)."""
    return teams_lookup.get(team_id, "")


def affected_games(season: Season, disruption: DisruptionInput,
                    teams_city_lookup: Optional[Dict[str, str]] = None) -> List[Game]:
    """Liefert die Liste der Spiele, die direkt von der Disruption betroffen sind."""
    out: List[Game] = []
    if isinstance(disruption, StadiumBlackout):
        for g in season.games:
            if disruption.affects(g.home, g.date):
                out.append(g)
    elif isinstance(disruption, WeatherWindow):
        if teams_city_lookup is None:
            raise ValueError("WeatherWindow braucht teams_city_lookup")
        for g in season.games:
            if (_city_of_team(g.home, teams_city_lookup) == disruption.city
                    and disruption.start_date <= g.date <= disruption.end_date):
                out.append(g)
    elif isinstance(disruption, MassPostponement):
        pk_set = set(disruption.game_pks)
        out = [g for g in season.games if g.game_pk in pk_set]
    else:
        raise TypeError(f"Unbekannter Disruption-Typ: {type(disruption)}")
    return out


def _blocked_dates(disruption: DisruptionInput) -> Set[date]:
    """Tage, an denen das/die betroffene Stadion/Stadt NICHT bespielt werden duerfen.

    Fuer MassPostponement: leeres Set, weil nur konkrete Spiel-PKs betroffen sind,
    nicht Tage.
    """
    if isinstance(disruption, (StadiumBlackout, WeatherWindow)):
        out: Set[date] = set()
        d = disruption.start_date
        while d <= disruption.end_date:
            out.add(d)
            d += timedelta(days=1)
        return out
    return set()


def _build_occupied_index(season: Season) -> Dict[str, Set[date]]:
    """Pro Team: Set der Tage, an denen das Team spielt."""
    out: Dict[str, Set[date]] = {}
    for g in season.games:
        out.setdefault(g.home, set()).add(g.date)
        out.setdefault(g.away, set()).add(g.date)
    return out


# ====================================================================
# Slot-Finder
# ====================================================================

def _streak_if_added(play_days: Set[date], d: date) -> int:
    """Laenge der konsekutiven Spieltag-Folge, die entsteht, wenn an Tag ``d``
    ein Spiel hinzukommt (verschmilzt angrenzende Runs; V(C)(12)-Zaehlung:
    konsekutive Kalender-SPIELTAGE, Doubleheader = 1 Tag)."""
    n = 1
    k = d - timedelta(days=1)
    while k in play_days:
        n += 1
        k -= timedelta(days=1)
    k = d + timedelta(days=1)
    while k in play_days:
        n += 1
        k += timedelta(days=1)
    return n


# CBA V(C)(12): ">20 konsekutive Spieltage" ist die Planungsgrenze ("scheduled,
# or rescheduled if practicable"); fuer Rainout-Makeups erlaubt der Vertrag
# explizit bis 24 fuer das Heimteam. Wir suchen deshalb ZWEISTUFIG: erst ein
# Slot, der beide Teams <= 20 haelt; nur wenn keiner existiert, bis <= 24
# (dokumentiert als "not practicable"-Fall). Verbatim:
# regulations/CBA_2022-2026_Article_V_Scheduling.md, V(C)(12).
VC12_STREAK_LIMIT = 20
VC12_RESCHEDULE_LIMIT = 24


def _find_next_free_slot(
    game: Game,
    season: Season,
    occupied: Dict[str, Set[date]],
    blocked_home_stadium: Set[date],
    home_team_constrained: bool,
    max_streak: int = VC12_STREAK_LIMIT,
) -> Optional[date]:
    """Findet den naechsten Tag nach `game.date`, an dem das Spiel platziert werden kann.

    Bedingungen:
    - im Saisonfenster
    - nicht im All-Star-Break
    - beide Teams frei (keine Doppelbuchung)
    - wenn home_team_constrained: Tag NICHT in blocked_home_stadium
      (StadiumBlackout/WeatherWindow gegen Heim)
    - Review-Fix P0-3 (2026-06-10): die Platzierung darf fuer KEINES der beiden
      Teams eine konsekutive Spieltag-Folge > ``max_streak`` erzeugen
      (CBA V(C)(12); vorher konnte ein Makeup z. B. einen 25-Tage-Streak bauen).
    """
    cur = game.date + timedelta(days=1)
    while cur <= season.season_end:
        if cur in season.all_star_dates:
            cur += timedelta(days=1)
            continue
        if home_team_constrained and cur in blocked_home_stadium:
            cur += timedelta(days=1)
            continue
        if cur in occupied.get(game.home, set()):
            cur += timedelta(days=1)
            continue
        if cur in occupied.get(game.away, set()):
            cur += timedelta(days=1)
            continue
        if (_streak_if_added(occupied.get(game.home, set()), cur) > max_streak
                or _streak_if_added(occupied.get(game.away, set()), cur) > max_streak):
            cur += timedelta(days=1)
            continue
        return cur
    return None


# ====================================================================
# Haupt-API
# ====================================================================

def repair_local(
    season: Season,
    disruption: DisruptionInput,
    teams_city_lookup: Optional[Dict[str, str]] = None,
) -> Tuple[Season, List[GameChange], List[Game]]:
    """Strategie A — Local Repair.

    Liefert (new_season, changes, unreschedulable).

    `unreschedulable` enthaelt Spiele, fuer die innerhalb der Saison kein
    Slot gefunden werden konnte. Diese Spiele BLEIBEN an ihrer Originalposition
    in `new_season.games` (M5, Sprint 2.10) — die Saison ist dann ein
    "Teil-Plan", der die Disruption-Bedingung fuer genau diese Spiele noch
    verletzt. Wichtig: `len(new_season.games) == len(season.games)` bleibt
    erhalten, damit Downstream-Reports (Revenue, Travel) nicht stillschweigend
    mit weniger Spielen rechnen. Im Milton-Massen-Fall ist `unreschedulable`
    typischerweise nicht leer — Local Repair ist dann formal nicht erfolgreich
    und der Orchestrator soll Strategie B oder C bevorzugen.
    """
    affected = affected_games(season, disruption, teams_city_lookup)
    affected_pks = {g.game_pk for g in affected}

    occupied = _build_occupied_index(season)
    blocked = _blocked_dates(disruption)

    # Beim Suchen muss das Heim-Stadion-Blackout fuer den ursprueglichen
    # Home-Team gelten (Spiel wird im Original-Heimstadion gespielt).
    home_constrained = isinstance(disruption, (StadiumBlackout, WeatherWindow))

    new_games: List[Game] = []
    changes: List[GameChange] = []
    unreschedulable: List[Game] = []

    for g in season.games:
        if g.game_pk not in affected_pks:
            new_games.append(g)
            continue

        # Aus occupied erstmal die alte Position entfernen, weil wir das
        # Spiel verschieben (sonst kollidiert es mit sich selbst).
        occupied[g.home].discard(g.date)
        occupied[g.away].discard(g.date)

        # Review-Fix P0-3: zweistufige V(C)(12)-konforme Slot-Suche —
        # bevorzugt <= 20 konsekutive Spieltage; nur wenn unmoeglich
        # ("if practicable"), bis zur expliziten Reschedule-Grenze 24.
        slot = _find_next_free_slot(g, season, occupied, blocked, home_constrained,
                                    max_streak=VC12_STREAK_LIMIT)
        slot_note = ""
        if slot is None:
            slot = _find_next_free_slot(g, season, occupied, blocked, home_constrained,
                                        max_streak=VC12_RESCHEDULE_LIMIT)
            if slot is not None:
                slot_note = (" [V(C)(12): kein <=20-Slot verfuegbar, Platzierung "
                             "innerhalb der 24-Tage-Reschedule-Grenze]")
        if slot is None:
            # M5 (Sprint 2.10): Spiel BLEIBT an seiner Originalposition in der
            # Saison (frueher wurde es stillschweigend geloescht, was die
            # Game-Anzahl senkte und Downstream-Revenue/Travel zu niedrig machte).
            # Es wird gleichzeitig in `unreschedulable` gemeldet, sodass Aufrufer
            # wissen, dass dieses Spiel die Disruption-Bedingung noch verletzt.
            # Damit gilt: len(new_season.games) == len(season.games).
            occupied[g.home].add(g.date)
            occupied[g.away].add(g.date)
            new_games.append(g)
            unreschedulable.append(g)
            continue

        new_g = Game(
            game_pk=g.game_pk,
            date=slot,
            home=g.home,
            away=g.away,
            venue=g.venue,
            doubleheader_seq=g.doubleheader_seq,
            game_type=g.game_type,
                dh_type=g.dh_type,
        )
        new_games.append(new_g)
        occupied[g.home].add(slot)
        occupied[g.away].add(slot)
        changes.append(GameChange(
            original_game_pk=g.game_pk,
            change_type="move",
            new_date=slot,
            note=f"Postponed from {g.date} to {slot}{slot_note}",
        ))

    new_games.sort(key=lambda g: (g.date, g.game_pk))
    new_season = Season(
        season=season.season,
        games=new_games,
        season_start=season.season_start,
        season_end=season.season_end,
        all_star_dates=season.all_star_dates,
    )
    return new_season, changes, unreschedulable
