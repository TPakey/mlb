"""Reduzierte Test-Instanz (P2-7).

Die vollen 30-Team-CP-SAT-Läufe (HAP, Phase B, voller Generator) brauchen
> 30–45 s und sind in der Sandbox nicht am Stück lauffähig (daher `@slow`,
CI-only). Für **schnelle lokale Smoke-Deckung** des Reise-/SA-Pfads liefert
dieses Modul eine reduzierte Instanz: nur die Spiele **innerhalb einer
Team-Teilmenge** (z. B. eine Division) aus einer realen Saison.

Damit lässt sich der Warm-Start-/`optimize_travel`-Pfad in < 5 s deterministisch
testen, ohne den vollen CP-SAT-Solve.
"""
from __future__ import annotations

from typing import List, Optional

from .season import Game, Season

# Bewährte kleine Cluster (geografisch/divisional) für schnelle Smokes.
AL_EAST = ("NYY", "BOS", "BAL", "TBR", "TOR")
AL_WEST = ("HOU", "SEA", "TEX", "LAA", "OAK")
NL_WEST = ("LAD", "SDP", "SFG", "ARI", "COL")


def build_reduced_season(full: Season, team_ids, *,
                         season: Optional[int] = None) -> Season:
    """Season nur mit Spielen, in denen **beide** Teams in ``team_ids`` liegen.

    Erhält Datumsfenster/All-Star-Break der Originalsaison. Das Ergebnis ist ein
    konsistenter Teilplan (Heim/Auswärts-Paarungen der Teilmenge), auf dem der
    SA-/Warm-Start-Pfad ohne CP-SAT lauffähig ist.
    """
    ts = set(team_ids)
    games: List[Game] = [g for g in full.games if g.home in ts and g.away in ts]
    return Season(
        season=season if season is not None else full.season,
        games=sorted(games, key=lambda g: (g.date, g.game_pk)),
        season_start=full.season_start,
        season_end=full.season_end,
        all_star_dates=full.all_star_dates,
    )
