"""Erzeugt einen realistisch-strukturierten Baseline-Spielplan.

Modellannahmen (Vereinfachung gegenüber dem echten MLB-Kalender):
- Jedes Team bestreitet exakt 1 Serie pro Wochen-Slot (kein Off-Week).
- Eine Serie umfasst 3 Spiele. Damit kommen wir bei 27 Slots auf 81 Spiele pro
  Team — eine "halbe MLB-Saison". Das System lässt sich auf 54 Slots erweitern;
  für Demonstrationszwecke und Solver-Laufzeit reichen 27.
- Pro Slot sind 15 Serien parallel (15 Heimteams + 15 Gastteams = 30 Teams).
- Heim/Auswärts wird so verteilt, dass jedes Team möglichst 13–14 Heimserien hat.
- Division-Rivalitäten bekommen leicht erhöhtes Gewicht in der Paarungsauswahl
  (jedes Team trifft jedes Divisionsteam mind. 2× pro Saison).

Diese Vereinfachung bewahrt die strukturellen Eigenschaften, die für den
Optimierer relevant sind (Reise-Trips, Heim-Stände, geografische Cluster),
ohne den Code mit der vollen MLB-Matchup-Matrix zu überladen.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Tuple

from ..data_loader import Team

NUM_SLOTS = 27          # Wochen-Slots (entspricht ~27 Wochen Saison)
SERIES_LENGTH = 3       # Spiele pro Serie
SEASON_START = date(2026, 3, 26)
ALL_STAR_BREAK = (date(2026, 7, 13), date(2026, 7, 16))


@dataclass
class Series:
    slot: int               # 0 .. NUM_SLOTS-1
    home: str               # Team-ID
    away: str               # Team-ID
    games: int = SERIES_LENGTH

    def involves(self, team_id: str) -> bool:
        return self.home == team_id or self.away == team_id

    def opponent_of(self, team_id: str) -> str:
        if self.home == team_id:
            return self.away
        if self.away == team_id:
            return self.home
        raise ValueError(f"Team {team_id} ist nicht in dieser Serie")

    def is_home_for(self, team_id: str) -> bool:
        return self.home == team_id


@dataclass
class Schedule:
    season: int
    series: List[Series] = field(default_factory=list)

    def for_team(self, team_id: str) -> List[Series]:
        return [s for s in self.series if s.involves(team_id)]

    def by_slot(self) -> Dict[int, List[Series]]:
        out: Dict[int, List[Series]] = {}
        for s in self.series:
            out.setdefault(s.slot, []).append(s)
        return out

    def venue_sequence(self, team_id: str) -> List[str]:
        """Liefert die Sequenz der Standorte (Stadion-Team-IDs) für ein Team
        über die Saison. Beim Heimspiel ist das die eigene ID, beim
        Auswärtsspiel die Heim-ID des Gegners."""
        out: List[str] = []
        for s in sorted(self.for_team(team_id), key=lambda x: x.slot):
            out.append(s.home)
        return out


def _round_robin_pairings(n: int, seed: int = 42) -> List[List[Tuple[int, int]]]:
    """Erzeugt einen kompletten Round-Robin-Plan für n Teams (n gerade).

    Berkamp/Circle-Methode: n-1 Runden, in denen jedes Team gegen jedes andere
    genau einmal antritt. Wir wiederholen das so oft wie nötig, um NUM_SLOTS
    Runden zu generieren, und rotieren dabei die Heim/Auswärts-Belegung.
    """
    assert n % 2 == 0, "n muss gerade sein"
    teams = list(range(n))
    rounds: List[List[Tuple[int, int]]] = []

    # Klassisches Round-Robin: n-1 Runden, fixiert Team 0
    fixed = teams[0]
    rotating = teams[1:]
    for _ in range(n - 1):
        pairs: List[Tuple[int, int]] = []
        pairs.append((fixed, rotating[-1]))
        half = (n - 1) // 2
        for i in range(half):
            pairs.append((rotating[i], rotating[-(i + 2)]))
        rounds.append(pairs)
        rotating = [rotating[-1]] + rotating[:-1]

    return rounds


def generate_baseline_schedule(teams: List[Team], seed: int = 42) -> Schedule:
    """Erzeugt einen vollständigen, regelkonformen Baseline-Spielplan."""
    rng = random.Random(seed)
    team_ids = [t.id for t in teams]
    n = len(team_ids)
    assert n == 30

    rr = _round_robin_pairings(n, seed=seed)

    # Wir brauchen NUM_SLOTS Runden — RR hat n-1 = 29 Runden, mehr als genug.
    # Wir nehmen die ersten NUM_SLOTS Runden und mischen die Reihenfolge leicht,
    # damit die geografische Cluster-Struktur nicht künstlich ideal ist.
    chosen = rr[:NUM_SLOTS]
    rng.shuffle(chosen)

    series_list: List[Series] = []
    home_count: Dict[str, int] = {tid: 0 for tid in team_ids}

    for slot_idx, pairs in enumerate(chosen):
        for a_idx, b_idx in pairs:
            a, b = team_ids[a_idx], team_ids[b_idx]
            # Heim-/Auswärts-Balance: Team mit weniger Heimserien wird Heim
            if home_count[a] < home_count[b]:
                home, away = a, b
            elif home_count[b] < home_count[a]:
                home, away = b, a
            else:
                home, away = (a, b) if rng.random() < 0.5 else (b, a)
            series_list.append(Series(slot=slot_idx, home=home, away=away))
            home_count[home] += 1

    sched = Schedule(season=2026, series=series_list)
    _sanity_check(sched, team_ids)
    return sched


def _sanity_check(sched: Schedule, team_ids: List[str]) -> None:
    # Jedes Team spielt jeden Slot genau eine Serie
    for slot, ss in sched.by_slot().items():
        playing = set()
        for s in ss:
            if s.home in playing or s.away in playing:
                raise AssertionError(f"Slot {slot}: Team doppelt eingeplant")
            playing.add(s.home)
            playing.add(s.away)
        if len(playing) != 30:
            raise AssertionError(f"Slot {slot}: {len(playing)} Teams aktiv (erwartet 30)")
    # Heim-Anzahl pro Team
    home_counts = {tid: 0 for tid in team_ids}
    for s in sched.series:
        home_counts[s.home] += 1
    counts = sorted(home_counts.values())
    if counts[-1] - counts[0] > 2:
        raise AssertionError(f"Heim-Balance verletzt: {home_counts}")


def slot_to_date(slot: int) -> date:
    """Konvertiert Slot-Index in den Mittags-Startdatum der zugehörigen Serie."""
    return SEASON_START + timedelta(days=slot * 7)
