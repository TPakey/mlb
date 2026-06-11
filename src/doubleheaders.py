"""Doubleheader-Planung (P1-2).

Reale MLB-Planer nutzen **Day-Night-Doubleheader** als Verdichtungswerkzeug: zwei
Spiele derselben Paarung am selben Tag/Ort. Das spart einen Kalendertag und
verkürzt damit eine Road-Trip-Spanne — nützlich, um eine zu lange Reise (AC-2.1.8,
> 13 Tage am Stück auswärts) unter das Limit zu bringen, ohne ein Spiel zu
streichen. Unser From-Scratch-Generator erzeugt bislang 0 DHs; der reale Plan ~29.

Kern-Operation: **Tail-Compression.** Eine Auswärts-Serie über L Tage (alle 1
Spiel/Tag) wird zu L-1 Tagen, indem die letzten beiden Spieltage zu einem
Day-Night-DH am vorletzten Tag zusammenfallen. Die Spielanzahl (Matchup-Quote)
bleibt **exakt erhalten**, die Belegung **schrumpft** (Teilmenge der alten Tage)
→ es entsteht garantiert kein neuer Overlap, und Break-Days/Blackouts, die der
ursprüngliche Plan respektierte, bleiben respektiert.

Anwendung: ``plan_doubleheaders_for_fatigue`` verdichtet gezielt die jeweils
letzte Auswärts-Serie eines zu langen Road-Trips, bis dessen Spanne ≤ Limit ist
(oder kein verdichtbarer Kandidat mehr existiert). Deterministisch.

Bewusste Grenze (v1): Verdichtet wird nur, wenn die **letzte** Auswärts-Serie des
Trips ≥ 2 Tage lang ist und noch keinen DH hat (kein Triple-Header). Endet der
Trip auf einer 1-Spiel-Serie, greift die Compression nicht — dokumentiert, kein
falsches Ergebnis. (Erweiterung: Compression + Pull-in der Folgeserien.)

Makeup-DHs (Wetter etc.) sind Sache des Disruption-Handlers; dieses Modul liefert
die Verdichtungs-Primitive und einen fatigue-gezielten Planer.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, Dict, List, Optional, Set, Tuple

from .season import Season
from .generator import GeneratorConfig
from .generator_optimizer import (
    SeriesEntry, _team_road_trips, _season_to_entries, _build_team_index,
    _entries_to_season, _no_team_overlap, _valid_start_for_length,
)


# ====================================================================
# Verdichtungs-Primitive (operieren auf SeriesEntry)
# ====================================================================

def series_game_count(entry: SeriesEntry) -> int:
    counts = entry.day_game_counts or tuple([1] * entry.length)
    return sum(counts)


def can_compress_tail(entry: SeriesEntry) -> bool:
    """True, wenn sich die letzten beiden Spieltage zu einem Day-Night-DH
    zusammenfassen lassen (Serie ≥ 2 Tage, beide Endtage genau 1 Spiel)."""
    if entry.length < 2:
        return False
    counts = entry.day_game_counts or tuple([1] * entry.length)
    return len(counts) >= 2 and counts[-1] == 1 and counts[-2] == 1


def compress_tail(entry: SeriesEntry) -> int:
    """Verdichtet die Serie um 1 Tag (Day-Night-DH am vorletzten Tag).

    Mutiert ``entry`` in place: ``length -= 1``, der vorletzte Spieltag bekommt
    2 Spiele. Gibt den (absoluten) Tag-Index des DH zurück. Erhält die
    Spielanzahl.
    """
    if not can_compress_tail(entry):
        raise ValueError(f"Serie {entry.idx} ist nicht verdichtbar (tail)")
    counts = list(entry.day_game_counts or tuple([1] * entry.length))
    last = counts.pop()
    counts[-1] += last
    entry.day_game_counts = tuple(counts)
    entry.length -= 1
    return entry.start_day + entry.length - 1


# ====================================================================
# Fatigue-gezielter Planer
# ====================================================================

@dataclass(frozen=True)
class DoubleheaderPlan:
    n_created: int
    created: List[Tuple[int, int, str, str]]   # (entry_idx, dh_day_idx, home, away)
    teams_helped: List[str]

    def summary(self) -> Dict[str, int]:
        return {"n_created": self.n_created, "n_teams_helped": len(self.teams_helped)}


def _last_away_series_of_trip(team_id: str, entries: List[SeriesEntry],
                              team_idx: Dict[str, List[int]],
                              trip: Tuple[int, int]) -> Optional[int]:
    """Index der Auswärts-Serie des Teams, die am letzten Tag des Trips endet."""
    first, last = trip
    best: Optional[int] = None
    best_end = -1
    for i in team_idx.get(team_id, []):
        e = entries[i]
        if e.away != team_id:
            continue
        e_end = e.start_day + e.length - 1
        if e.start_day >= first and e_end <= last and e_end > best_end:
            best_end = e_end
            best = i
    return best


def _team_away_in_trip(team_id: str, entries: List[SeriesEntry],
                       team_idx: Dict[str, List[int]],
                       trip: Tuple[int, int]) -> List[int]:
    """Auswärts-Serien-Indizes des Teams vollständig innerhalb des Trips,
    sortiert nach Start-Tag."""
    first, last = trip
    out: List[int] = []
    for i in team_idx.get(team_id, []):
        e = entries[i]
        if e.away != team_id:
            continue
        e_end = e.start_day + e.length - 1
        if e.start_day >= first and e_end <= last:
            out.append(i)
    out.sort(key=lambda i: entries[i].start_day)
    return out


def compress_with_pullin(
    entries: List[SeriesEntry],
    team_idx: Dict[str, List[int]],
    team_id: str,
    trip: Tuple[int, int],
    *,
    is_valid_start: Optional[Callable[[SeriesEntry, int], bool]] = None,
) -> Optional[int]:
    """DH-Compression **v2** (Compression + Pull-in).

    Greift auch dann, wenn die LETZTE Auswärts-Serie des Trips nur 1 Spiel hat
    (v1 = no-op). Vorgehen: die späteste verdichtbare *innere* Serie des Trips
    wird per Tail-Compression um 1 Tag verkürzt; anschließend werden alle
    Folgeserien innerhalb des Trips um genau 1 Tag **nachgezogen** (Pull-in) →
    der letzte Auswärtstag rückt um 1 vor → **Trip-Spanne −1**.

    Garantien:
    - **Matchup-erhaltend** (kein Spiel hinzugefügt/entfernt; nur ein DH gebildet
      und Folgeserien verschoben).
    - **Validiert**: jede nachgezogene Serie wird auf NoOverlap (beide Teams) und
      — falls ``is_valid_start`` übergeben — auf Break-Day-/Blackout-Gültigkeit
      geprüft. Bei *irgendeinem* Fehlschlag wird der gesamte Zug atomar
      zurückgerollt (kein Teil-Move).
    - **Deterministisch** (Auswahl der spätesten verdichtbaren Serie, feste
      Reihenfolge).

    Gibt den DH-Tag-Index zurück oder ``None`` (kein zulässiger Zug). Mutiert
    ``entries`` nur bei Erfolg.
    """
    series = _team_away_in_trip(team_id, entries, team_idx, trip)
    if len(series) < 2:
        return None
    last_idx = series[-1]
    # Späteste verdichtbare Serie, die NICHT die letzte ist (die letzte wäre v1).
    candidates = [i for i in series
                  if i != last_idx and can_compress_tail(entries[i])]
    if not candidates:
        return None
    ci = max(candidates, key=lambda i: entries[i].start_day)
    followers = [i for i in series if entries[i].start_day > entries[ci].start_day]
    if not followers:
        return None
    snap = {i: (entries[i].length, entries[i].day_game_counts, entries[i].start_day)
            for i in [ci, *followers]}
    dh_day = compress_tail(entries[ci])     # ci.length −1, freier Tag am Ende
    ok = True
    for i in followers:                      # earliest-first (series ist sortiert)
        new_start = entries[i].start_day - 1
        if is_valid_start is not None and not is_valid_start(entries[i], new_start):
            ok = False
            break
        entries[i].start_day = new_start
        if not _no_team_overlap(entries, team_idx, i):
            ok = False
            break
    if ok:
        return dh_day
    # Atomarer Revert (Länge, counts, start_day).
    for i, (L, c, s) in snap.items():
        entries[i].length = L
        entries[i].day_game_counts = c
        entries[i].start_day = s
    return None


def plan_doubleheaders_for_fatigue(
    entries: List[SeriesEntry],
    team_idx: Dict[str, List[int]],
    *,
    away_limit: int = 13,
    max_per_team: int = 4,
    enable_pullin: bool = False,
    is_valid_start: Optional[Callable[[SeriesEntry, int], bool]] = None,
) -> DoubleheaderPlan:
    """Verdichtet zu lange Road-Trips per Day-Night-DH (mutiert ``entries``).

    Für jedes Team werden zu lange Road-Trips (Spanne > ``away_limit``) der
    Reihe nach behandelt: die letzte Auswärts-Serie des längsten über-Limit-
    Trips wird per Tail-Compression um 1 Tag verkürzt → Spanne −1. Wiederholt,
    bis konform oder kein verdichtbarer Kandidat. Deterministisch (Teams nach
    ID sortiert), matchup-erhaltend, kein neuer Overlap.
    """
    created: List[Tuple[int, int, str, str]] = []
    teams_helped: List[str] = []
    for team_id in sorted(team_idx):
        helped = 0
        guard = 0
        while helped < max_per_team and guard < 30:
            guard += 1
            trips = _team_road_trips(team_id, entries, team_idx)
            over = [t for t in trips if (t[1] - t[0] + 1) > away_limit]
            if not over:
                break
            trip = max(over, key=lambda t: t[1] - t[0])
            i = _last_away_series_of_trip(team_id, entries, team_idx, trip)
            if i is not None and can_compress_tail(entries[i]):
                # v1: Tail-Compression der letzten Trip-Serie (Spanne −1).
                dh_day = compress_tail(entries[i])
                e = entries[i]
                created.append((i, dh_day, e.home, e.away))
                helped += 1
                continue
            if enable_pullin:
                # v2: letzte Serie nicht verdichtbar (z. B. 1 Spiel) → innere
                # Serie verdichten + Folgeserien nachziehen (Spanne −1).
                dh_day = compress_with_pullin(
                    entries, team_idx, team_id, trip,
                    is_valid_start=is_valid_start)
                if dh_day is not None:
                    # Welche Serie trägt jetzt den DH? (die mit 2 Spielen am dh_day)
                    for j in _team_away_in_trip(team_id, entries, team_idx,
                                                (trip[0], trip[1] - 1)):
                        e = entries[j]
                        if e.start_day <= dh_day < e.start_day + e.length:
                            created.append((j, dh_day, e.home, e.away))
                            break
                    helped += 1
                    continue
            break
        if helped:
            teams_helped.append(team_id)
    return DoubleheaderPlan(n_created=len(created), created=created,
                            teams_helped=teams_helped)


# ====================================================================
# Saison-Level-Komfort (Roundtrip)
# ====================================================================

def _build_is_valid_start(cfg: GeneratorConfig, total_days: int,
                          ) -> Callable[[SeriesEntry, int], bool]:
    """Validator für Pull-in-Ziele: Break-Days (All-Star + ggf. periodisch) und
    team-spezifische Heim-Blackouts (home_blackout_days). Konsistent mit der
    SA-Gültigkeitsprüfung in optimize_travel."""
    break_days: Set[int] = set()
    if cfg.all_star_break:
        d = cfg.all_star_break[0]
        while d <= cfg.all_star_break[1]:
            break_days.add((d - cfg.season_start).days)
            d += timedelta(days=1)
    if cfg.enforce_fatigue_constraints:
        from .generator import _periodic_break_days
        break_days |= _periodic_break_days(total_days, max_gap=21)
    lengths = set()
    blackout = cfg.home_blackout_days or {}

    def _ok(entry: SeriesEntry, start: int) -> bool:
        if start < 0 or start + entry.length > total_days:
            return False
        if entry.length not in lengths:
            lengths.add(entry.length)
            _valid_cache[entry.length] = _valid_start_for_length(
                entry.length, total_days, break_days)
        if start not in _valid_cache[entry.length]:
            return False
        bl = blackout.get(entry.home)
        if bl:
            for k in range(entry.length):
                if (start + k) in bl:
                    return False
        return True

    _valid_cache: Dict[int, Set[int]] = {}
    return _ok


def compress_for_fatigue(
    season: Season,
    cfg: GeneratorConfig,
    *,
    away_limit: int = 13,
    max_per_team: int = 4,
    enable_pullin: bool = False,
) -> Tuple[Season, DoubleheaderPlan]:
    """Wendet die fatigue-gezielte DH-Verdichtung auf eine Saison an.

    Zerlegt die Saison in Serien-Einträge, verdichtet, baut zurück. Die
    resultierende Saison enthält echte Day-Night-DH (doubleheader_seq 1/2) und
    hat ggf. kürzere Road-Trips. Spielanzahl je Team bleibt erhalten.

    ``enable_pullin=True`` aktiviert die v2-Erweiterung (Compression + Pull-in):
    greift auch, wenn die letzte Trip-Serie nicht verdichtbar ist. Pull-in-Ziele
    werden gegen Break-Days/Blackouts validiert (aus ``cfg`` abgeleitet).
    """
    entries = _season_to_entries(season, cfg)
    team_idx = _build_team_index(entries)
    total_days = (cfg.season_end - cfg.season_start).days + 1
    validator = _build_is_valid_start(cfg, total_days) if enable_pullin else None
    plan = plan_doubleheaders_for_fatigue(
        entries, team_idx, away_limit=away_limit, max_per_team=max_per_team,
        enable_pullin=enable_pullin, is_valid_start=validator)
    new_season = _entries_to_season(entries, cfg, season.all_star_dates)
    return new_season, plan
