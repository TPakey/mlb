"""Loader für externe Schedule-Datenquellen.

Aktuell unterstützt:
- MLB Stats API JSON (https://statsapi.mlb.com/api/v1/schedule)

Die API liefert JSON dieser Form:
{
  "dates": [
    {
      "date": "2024-03-28",
      "games": [
        {
          "gamePk": 745811,
          "gameDate": "2024-03-28T17:10:00Z",
          "gameType": "R",
          "doubleHeader": "N",  // "N"=none, "S"=split, "Y"=trad
          "gameNumber": 1,
          "teams": {
            "away": { "team": { "id": 119, "name": "Los Angeles Dodgers", "abbreviation": "LAD" } },
            "home": { "team": { "id": 137, "name": "San Diego Padres",   "abbreviation": "SD" } }
          },
          "venue": { "id": 2680, "name": "Petco Park" },
          "status": { "abstractGameState": "Final" }
        }
      ]
    }
  ]
}

Wir mappen die MLB-Team-IDs auf unsere internen drei-Buchstaben-Codes
(siehe teams.json) über die offiziell verwendeten Abkürzungen.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from .data_loader import load_teams
from .season import Game, Season


# Mapping von MLB-Stats-API-Team-IDs auf unsere internen Codes.
# Stand: stabile MLB-Team-IDs.
MLB_TEAM_ID_TO_CODE: Dict[int, str] = {
    108: "LAA",  # Los Angeles Angels
    109: "ARI",  # Arizona Diamondbacks
    110: "BAL",  # Baltimore Orioles
    111: "BOS",  # Boston Red Sox
    112: "CHC",  # Chicago Cubs
    113: "CIN",  # Cincinnati Reds
    114: "CLE",  # Cleveland Guardians
    115: "COL",  # Colorado Rockies
    116: "DET",  # Detroit Tigers
    117: "HOU",  # Houston Astros
    118: "KCR",  # Kansas City Royals
    119: "LAD",  # Los Angeles Dodgers
    120: "WSN",  # Washington Nationals
    121: "NYM",  # New York Mets
    133: "OAK",  # Athletics (offizieller MLB-Name seit 2025)
    134: "PIT",  # Pittsburgh Pirates
    135: "SDP",  # San Diego Padres
    136: "SEA",  # Seattle Mariners
    137: "SFG",  # San Francisco Giants
    138: "STL",  # St. Louis Cardinals
    139: "TBR",  # Tampa Bay Rays
    140: "TEX",  # Texas Rangers
    141: "TOR",  # Toronto Blue Jays
    142: "MIN",  # Minnesota Twins
    143: "PHI",  # Philadelphia Phillies
    144: "ATL",  # Atlanta Braves
    145: "CWS",  # Chicago White Sox
    146: "MIA",  # Miami Marlins
    147: "NYY",  # New York Yankees
    158: "MIL",  # Milwaukee Brewers
}

# Fallback-Mapping über offizielle Abkürzungen, falls eine ID nicht im Dict ist
MLB_ABBR_TO_CODE: Dict[str, str] = {
    "LAA": "LAA", "ARI": "ARI", "BAL": "BAL", "BOS": "BOS", "CHC": "CHC",
    "CIN": "CIN", "CLE": "CLE", "COL": "COL", "DET": "DET", "HOU": "HOU",
    "KC":  "KCR", "KCR": "KCR",
    "LAD": "LAD", "WSH": "WSN", "WSN": "WSN",
    "NYM": "NYM",
    "OAK": "OAK", "ATH": "OAK",  # Athletics ab 2025 mit "ATH"
    "PIT": "PIT", "SD":  "SDP", "SDP": "SDP", "SEA": "SEA", "SF":  "SFG", "SFG": "SFG",
    "STL": "STL", "TB":  "TBR", "TBR": "TBR", "TEX": "TEX", "TOR": "TOR", "MIN": "MIN",
    "PHI": "PHI", "ATL": "ATL", "CWS": "CWS", "CHW": "CWS",
    "MIA": "MIA", "NYY": "NYY", "MIL": "MIL",
}


class ScheduleLoaderError(Exception):
    pass


def _resolve_team_code(team_block: dict) -> Optional[str]:
    """Aus dem 'team'-Block der API einen internen Code ableiten."""
    tid = team_block.get("id")
    if tid in MLB_TEAM_ID_TO_CODE:
        return MLB_TEAM_ID_TO_CODE[tid]
    abbr = team_block.get("abbreviation") or ""
    if abbr in MLB_ABBR_TO_CODE:
        return MLB_ABBR_TO_CODE[abbr]
    # Letzter Fallback: aus dem Namen — sollte nicht passieren
    return None


def load_mlb_schedule_json(
    path: Path,
    season: Optional[int] = None,
    game_type: str = "R",
) -> Season:
    """Lädt ein MLB-Stats-API-JSON und gibt eine `Season`-Instanz zurück.

    Args:
        path: Pfad zur JSON-Datei (gespeicherte Antwort des Schedule-Endpunkts).
        season: Optional. Wenn None, wird aus den Daten abgeleitet.
        game_type: Nur Spiele dieses Typs übernehmen ("R"=Regular Season).
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if "dates" not in raw:
        raise ScheduleLoaderError(
            f"Unerwartete JSON-Struktur in {path}: kein 'dates'-Feld. "
            f"Top-Level-Keys: {list(raw.keys())}"
        )

    games: List[Game] = []
    skipped: Dict[str, int] = {
        "wrong_type": 0, "unmapped_team": 0, "postponed": 0, "cancelled": 0,
    }

    # Statusfilter: nur tatsächlich gespielte Spiele behalten.
    # MLB Stats API listet "Postponed" Spiele als Duplikate zum Makeup-Termin —
    # ohne Filter würden Reisedistanzen falsch berechnet.
    PLAYED_STATES = {"Final", "Completed Early", "Game Over"}

    for day_entry in raw["dates"]:
        day = date.fromisoformat(day_entry["date"])
        for game_raw in day_entry.get("games", []):
            gt = game_raw.get("gameType", "?")
            if gt != game_type:
                skipped["wrong_type"] += 1
                continue
            status = (game_raw.get("status") or {}).get("detailedState", "")
            if status not in PLAYED_STATES:
                # Postponed / Cancelled / Suspended / Scheduled ohne Outcome
                if status == "Postponed":
                    skipped["postponed"] += 1
                elif status == "Cancelled":
                    skipped["cancelled"] += 1
                else:
                    skipped[status.lower().replace(" ", "_")] = (
                        skipped.get(status.lower().replace(" ", "_"), 0) + 1
                    )
                continue
            home_code = _resolve_team_code(game_raw["teams"]["home"]["team"])
            away_code = _resolve_team_code(game_raw["teams"]["away"]["team"])
            if not home_code or not away_code:
                skipped["unmapped_team"] += 1
                continue
            venue = (game_raw.get("venue") or {}).get("name") or home_code
            dh_seq = 0
            dh_type = ""
            raw_dh = game_raw.get("doubleHeader", "N")
            if raw_dh != "N":
                dh_seq = int(game_raw.get("gameNumber", 1))
                # Review-Fix Runde 2 (Punkt 1): Typ erhalten (S=split, Y=trad.)
                dh_type = raw_dh
            games.append(Game(
                game_pk=int(game_raw.get("gamePk", 0)),
                date=day,
                home=home_code,
                away=away_code,
                venue=venue,
                doubleheader_seq=dh_seq,
                game_type=gt,
                dh_type=dh_type,
            ))

    if not games:
        raise ScheduleLoaderError(
            f"Keine Spiele geladen. Übersprungen: {skipped}"
        )

    derived_season = season or games[0].date.year
    return Season(
        season=derived_season,
        games=sorted(games, key=lambda g: (g.date, g.doubleheader_seq, g.game_pk)),
        season_start=min(g.date for g in games),
        season_end=max(g.date for g in games),
    )


def quick_diagnose(path: Path) -> Dict[str, object]:
    """Schnell-Diagnose einer eingelesenen JSON-Datei (für Sanity-Checks)."""
    try:
        season = load_mlb_schedule_json(path)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    teams = load_teams()
    known_ids = {t.id for t in teams}
    unknown_home = {g.home for g in season.games} - known_ids
    unknown_away = {g.away for g in season.games} - known_ids
    return {
        "ok": True,
        "season": season.season,
        "stats": season.stats(),
        "unknown_home_team_codes": sorted(unknown_home),
        "unknown_away_team_codes": sorted(unknown_away),
    }
