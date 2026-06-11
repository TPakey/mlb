"""Realistisches Saisonmodell — Spiele, Serien, ganze Saison.

Im Gegensatz zum `schedule_generator.py` aus Sprint 0 (vereinfachtes
Wochen-Slot-Modell, 81 Spiele pro Team) modelliert dieses Modul die echte
MLB-Saison auf Tagesebene:

- jedes einzelne Spiel hat ein Datum, ein Heimteam, ein Auswärtsteam,
  optional eine Doubleheader-Sequenz
- Serien (Series) werden aus konsekutiven Spielen derselben Paarung am selben
  Ort abgeleitet — Länge ist also 1–4 Spiele
- Off-Days sind Tage ohne Spiel für ein bestimmtes Team
- Reisetage entstehen implizit zwischen dem Ende einer Serie und dem Beginn
  der nächsten

Dieses Modell ist die Datenstruktur, in die der MLB-Stats-API-Loader übersetzt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, Iterator, List, Optional, Tuple


@dataclass(frozen=True)
class Game:
    """Ein einzelnes Spiel."""
    game_pk: int               # Eindeutige Spiel-ID (MLB Stats API gamePk)
    date: date
    home: str                  # Team-ID des Heimteams
    away: str                  # Team-ID des Auswärtsteams
    venue: str                 # Stadion-Name (oder Team-ID, falls Heimstadion)
    doubleheader_seq: int = 0  # 0 = kein DH, 1/2 = erstes/zweites DH-Spiel
    game_type: str = "R"       # R=Regular, P=Postseason, S=Spring, etc.
    # Review-Fix Runde 2 (Punkt 1): MLB-Stats-API `doubleHeader`-Typ erhalten —
    # "S"=split (getrennte Tickets), "Y"=traditional, ""/"N"=kein DH. Noetig
    # fuer V(C)(14) Satz 2 ("one home split doubleheader per Club"), der vorher
    # als "nicht pruefbar" galt, weil der Loader den Typ wegwarf.
    dh_type: str = ""

    def involves(self, team_id: str) -> bool:
        return self.home == team_id or self.away == team_id

    def opponent_of(self, team_id: str) -> str:
        if self.home == team_id:
            return self.away
        if self.away == team_id:
            return self.home
        raise ValueError(f"Team {team_id} ist nicht in diesem Spiel")

    def is_home_for(self, team_id: str) -> bool:
        return self.home == team_id


@dataclass(frozen=True)
class GameSeries:
    """Eine zusammenhängende Serie mehrerer Spiele.

    Aus aufeinanderfolgenden Spielen am selben Ort zwischen denselben beiden
    Teams gebildet. Reisen zwischen den Spielen einer Serie sind null
    (gleicher Ort), Reisen vor/nach der Serie sind die Hauptkostenfaktoren.
    """
    home: str
    away: str
    games: Tuple[Game, ...]

    @property
    def start_date(self) -> date:
        return min(g.date for g in self.games)

    @property
    def end_date(self) -> date:
        return max(g.date for g in self.games)

    @property
    def length(self) -> int:
        return len(self.games)

    @property
    def venue(self) -> str:
        return self.games[0].venue

    def involves(self, team_id: str) -> bool:
        return self.home == team_id or self.away == team_id

    def is_home_for(self, team_id: str) -> bool:
        return self.home == team_id


@dataclass
class Season:
    """Volle Saison mit allen Spielen und abgeleiteten Strukturen."""
    season: int
    games: List[Game] = field(default_factory=list)
    season_start: Optional[date] = None
    season_end: Optional[date] = None
    all_star_dates: Tuple[date, ...] = field(default_factory=tuple)

    # ------- Abfragen -------

    def games_for_team(self, team_id: str) -> List[Game]:
        return sorted(
            (g for g in self.games if g.involves(team_id)),
            key=lambda g: (g.date, g.doubleheader_seq),
        )

    def games_on(self, day: date) -> List[Game]:
        return [g for g in self.games if g.date == day]

    def home_games(self, team_id: str) -> List[Game]:
        return [g for g in self.games if g.home == team_id]

    def away_games(self, team_id: str) -> List[Game]:
        return [g for g in self.games if g.away == team_id]

    # ------- Abgeleitete Strukturen -------

    def series_for_team(self, team_id: str) -> List[GameSeries]:
        """Bildet Serien aus konsekutiven Spielen am selben Ort gegen denselben Gegner."""
        gs = self.games_for_team(team_id)
        if not gs:
            return []

        out: List[GameSeries] = []
        cur: List[Game] = [gs[0]]
        for g in gs[1:]:
            prev = cur[-1]
            same_pair = ({prev.home, prev.away} == {g.home, g.away})
            same_venue = prev.venue == g.venue
            # Lückenlos: heute oder morgen (Doubleheader = selber Tag, dann Folgetag)
            gap = (g.date - prev.date).days
            consecutive = gap <= 1
            if same_pair and same_venue and consecutive:
                cur.append(g)
            else:
                out.append(GameSeries(home=cur[0].home, away=cur[0].away, games=tuple(cur)))
                cur = [g]
        out.append(GameSeries(home=cur[0].home, away=cur[0].away, games=tuple(cur)))
        return out

    def venue_sequence(self, team_id: str) -> List[Tuple[date, str]]:
        """Liefert für ein Team eine Liste (date, venue_team_id) für jeden Spieltag.

        Verwendet zur Berechnung von Reisedistanz und Off-Day-Erholung.
        """
        return [(g.date, g.home) for g in self.games_for_team(team_id)]

    def off_days(self, team_id: str, start: Optional[date] = None,
                 end: Optional[date] = None) -> List[date]:
        """Tage ohne Spiel zwischen Saisonstart und Saisonende für ein Team."""
        gs = self.games_for_team(team_id)
        if not gs:
            return []
        s = start or min(g.date for g in gs)
        e = end or max(g.date for g in gs)
        play_dates = {g.date for g in gs}
        out: List[date] = []
        d = s
        while d <= e:
            if d not in play_dates:
                out.append(d)
            d += timedelta(days=1)
        return out

    # ------- Aggregat-Statistiken -------

    def stats(self) -> Dict[str, int]:
        """Quick-Check der Saison-Struktur."""
        teams = {g.home for g in self.games} | {g.away for g in self.games}
        games_per_team: Dict[str, int] = {t: 0 for t in teams}
        home_per_team: Dict[str, int] = {t: 0 for t in teams}
        for g in self.games:
            games_per_team[g.home] += 1
            games_per_team[g.away] += 1
            home_per_team[g.home] += 1
        return {
            "teams": len(teams),
            "games_total": len(self.games),
            "games_per_team_min": min(games_per_team.values()) if games_per_team else 0,
            "games_per_team_max": max(games_per_team.values()) if games_per_team else 0,
            "home_per_team_min": min(home_per_team.values()) if home_per_team else 0,
            "home_per_team_max": max(home_per_team.values()) if home_per_team else 0,
            "doubleheaders": sum(1 for g in self.games if g.doubleheader_seq > 0) // 2,
            "first_date": min(g.date for g in self.games).isoformat() if self.games else None,
            "last_date": max(g.date for g in self.games).isoformat() if self.games else None,
        }

    def __iter__(self) -> Iterator[Game]:
        return iter(self.games)

    def __len__(self) -> int:
        return len(self.games)


def detect_all_star_break(season: "Season") -> Optional[Tuple[date, date]]:
    """Erkennt den All-Star-Break als laengste liga-weite spielfreie Luecke in
    der Saisonmitte (typisch 3-4 Tage Mitte Juli).

    Scannt die distinkten Spieltage; die laengste Folge aufeinanderfolgender Tage
    OHNE Spiel im mittleren Saisondrittel gilt als ASB. Gibt None zurueck, wenn
    keine plausible Luecke (>= 3 Tage Abstand) gefunden wird.

    Gemeinsam genutzt von tools/backtest.py (Vergleich) und src/main.py
    (Warm-Start), damit der SA-Optimizer den Break respektiert.
    """
    if not season.games:
        return None
    play_days = sorted({g.date for g in season.games})
    start, end = play_days[0], play_days[-1]
    mid_lo = start + timedelta(days=int((end - start).days * 0.35))
    mid_hi = start + timedelta(days=int((end - start).days * 0.65))
    best: Optional[Tuple[date, date]] = None
    best_len = 1
    for a, b in zip(play_days, play_days[1:]):
        gap = (b - a).days
        if gap >= 3 and mid_lo <= a <= mid_hi and gap > best_len:
            best_len = gap
            best = (a + timedelta(days=1), b - timedelta(days=1))
    return best
