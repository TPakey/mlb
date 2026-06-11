"""Matchup-Quoten-Extractor.

Liefert aus einer echten Saison die Matchup-Struktur:
- Welches Team-Paar spielt sich wie oft, wo (Heim)?
- Wie sind die Spiele in Serien gruppiert (Anzahl, Laengen)?

Diese Quoten sind die *Inputs* fuer den from-Scratch-Generator. Sie sind
unabhaengig vom konkreten Plan - sie ergeben sich aus den MLB-Liga-Regeln
(13 vs Division-Rival, 6 vs Liga-non-Div, etc.) und sind somit eine legitime
Eingabe fuer die Generierung.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .season import Season


@dataclass(frozen=True)
class SeriesTemplate:
    """Eine zu plazierende Serie: Heim-Team, Gegner, Anzahl Spiele.

    Wird vom Generator als Input genommen und einer konkreten Datums-Slot
    zugewiesen.
    """
    home: str
    away: str
    length: int               # Anzahl Spiele in der Serie (2/3/4)


@dataclass
class MatchupQuotas:
    """Aggregierte Matchup-Struktur einer Saison.

    `series_templates` ist die kanonische Eingabe fuer den Generator: die Liste
    aller zu plazierenden Serien, mit Heimteam, Gegner und Laenge.
    """
    season: int
    series_templates: List[SeriesTemplate] = field(default_factory=list)

    @property
    def total_series(self) -> int:
        return len(self.series_templates)

    @property
    def total_games(self) -> int:
        return sum(s.length for s in self.series_templates)

    def home_count(self, team_id: str) -> int:
        return sum(s.length for s in self.series_templates if s.home == team_id)

    def away_count(self, team_id: str) -> int:
        return sum(s.length for s in self.series_templates if s.away == team_id)

    def games_per_team(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for s in self.series_templates:
            out[s.home] = out.get(s.home, 0) + s.length
            out[s.away] = out.get(s.away, 0) + s.length
        return out

    def series_length_distribution(self) -> Dict[int, int]:
        return dict(Counter(s.length for s in self.series_templates))

    def matchup_counts(self) -> Dict[Tuple[str, str], int]:
        """(home, away) -> Anzahl Spiele."""
        out: Dict[Tuple[str, str], int] = {}
        for s in self.series_templates:
            key = (s.home, s.away)
            out[key] = out.get(key, 0) + s.length
        return out


def extract_matchup_quotas(season: Season) -> MatchupQuotas:
    """Leitet aus einer echten Saison die Serien-Templates ab.

    Methode: pro Team identifizieren wir alle Serien (konsekutive Spiele
    selber Ort, selber Gegner), nehmen die als Template auf.
    """
    seen_series_ids: set = set()
    templates: List[SeriesTemplate] = []

    # Wir sammeln Serien aus jeder Team-Sicht; vermeiden Duplikate ueber
    # einen Identifier (home, away, start_date)
    teams_in_season = set()
    for g in season.games:
        teams_in_season.add(g.home)
        teams_in_season.add(g.away)

    for team_id in teams_in_season:
        for series in season.series_for_team(team_id):
            # Dedup-Key: home, away, start_date
            key = (series.home, series.away, series.start_date.isoformat())
            if key in seen_series_ids:
                continue
            seen_series_ids.add(key)
            templates.append(SeriesTemplate(
                home=series.home,
                away=series.away,
                length=series.length,
            ))

    return MatchupQuotas(season=season.season, series_templates=templates)
