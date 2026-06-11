"""SportsDataIO-Adapter — kommerzielle, normalisierte Sport-Daten-API.

Verwendete Endpoints (alle erfordern den Plan-Key):
- GET /v3/mlb/scores/json/Games/{season}    — alle Spiele einer Saison
- GET /v3/mlb/scores/json/teams             — Team-Stammdaten
- GET /v3/mlb/scores/json/Stadiums          — Stadien

Beispiel-Game-Objekt (vereinfacht):
{
  "GameID": 17541,
  "Season": 2024,
  "SeasonType": 1,   // 1=Regular
  "Status": "Final",
  "Day": "2024-03-28T00:00:00",
  "DateTime": "2024-03-28T22:10:00",
  "AwayTeam": "LAD",
  "HomeTeam": "SD",
  "StadiumID": 56,
  "Channel": "ESPN",
  "DoubleHeader": false,
  ...
}
"""
from __future__ import annotations

import json
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, List, Optional

from ..config import require_sportsdataio_key
from ..loaders import MLB_ABBR_TO_CODE
from ..season import Game, Season
from .base import DataSourceAdapter, DataSourceError


BASE_URL = "https://api.sportsdata.io/v3/mlb"


def _normalize_abbr(abbr: str) -> Optional[str]:
    """SportsDataIO nutzt teils andere Abkürzungen als die offiziellen.
    Wir mappen sie auf unsere internen Codes."""
    if not abbr:
        return None
    return MLB_ABBR_TO_CODE.get(abbr.upper())


def _parse_date(s: str) -> date:
    """Sowohl 'YYYY-MM-DDTHH:MM:SS' als auch 'YYYY-MM-DD' parsen."""
    if not s:
        raise ValueError("Leeres Datum")
    if "T" in s:
        return datetime.fromisoformat(s.replace("Z", "")).date()
    return date.fromisoformat(s)


def games_from_sportsdataio_payload(games_raw: Iterable[dict], season: int) -> Season:
    """Wandelt eine Liste SportsDataIO-Game-Objekte in eine `Season` um."""
    games: List[Game] = []
    skipped = {"non_regular": 0, "unmapped_team": 0, "no_date": 0, "no_pk": 0}
    seen_pks: set = set()
    for g in games_raw:
        season_type = g.get("SeasonType", 1)
        if season_type != 1:   # 1 = Regular Season
            skipped["non_regular"] += 1
            continue
        day_str = g.get("Day") or g.get("DateTime")
        if not day_str:
            skipped["no_date"] += 1
            continue
        try:
            day = _parse_date(day_str)
        except ValueError:
            skipped["no_date"] += 1
            continue
        home = _normalize_abbr(g.get("HomeTeam", ""))
        away = _normalize_abbr(g.get("AwayTeam", ""))
        if not home or not away:
            skipped["unmapped_team"] += 1
            continue
        # Audit A5 (Sprint A-1): game_pk-Kollisionen abfangen. Vorher fielen
        # alle Spiele ohne GameID auf 0 zurück, was Set-Dedup-Bugs verursacht.
        raw_pk = g.get("GameID")
        if raw_pk is None or int(raw_pk) == 0 or int(raw_pk) in seen_pks:
            skipped["no_pk"] += 1
            continue
        game_pk = int(raw_pk)
        seen_pks.add(game_pk)
        dh_seq = 0
        if g.get("DoubleHeader"):
            dh_seq = int(g.get("GameNumber", 1))
        games.append(Game(
            game_pk=game_pk,
            date=day,
            home=home,
            away=away,
            venue=g.get("StadiumID") and str(g["StadiumID"]) or home,
            doubleheader_seq=dh_seq,
            game_type="R",
        ))
    if not games:
        raise DataSourceError(
            f"Kein Regular-Season-Spiel aus SportsDataIO-Payload extrahiert. "
            f"Übersprungen: {skipped}"
        )
    return Season(
        season=season,
        games=sorted(games, key=lambda x: (x.date, x.doubleheader_seq, x.game_pk)),
        season_start=min(g.date for g in games),
        season_end=max(g.date for g in games),
    )


class SportsDataIoAdapter(DataSourceAdapter):
    """Konkreter Adapter für die SportsDataIO-MLB-API."""

    name = "sportsdata_io"

    def __init__(self, api_key: Optional[str] = None, timeout_seconds: int = 30,
                 cache_dir: Optional[Path] = None):
        self.api_key = api_key or require_sportsdataio_key()
        self.timeout = timeout_seconds
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _http_get(self, endpoint: str) -> list:
        """HTTP-GET mit Key im Header (Audit A2, Sprint A-1).

        Der frühere Code legte den API-Key in den URL-Querystring (`?key=...`),
        was Keys in Proxy-/CDN-/Browser-Logs sichtbar machte. SportsDataIO
        unterstützt den Standard-Header `Ocp-Apim-Subscription-Key`, der nicht
        in URL-basierten Logs landet.
        """
        url = f"{BASE_URL}{endpoint}"
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "MLB-Logistics-Optimizer/0.2",
                    "Ocp-Apim-Subscription-Key": self.api_key,
                },
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise DataSourceError(f"HTTP-Fehler bei {endpoint}: {exc}") from exc

    def fetch_season_schedule(self, season: int, game_type: str = "R") -> Season:
        cache_path: Optional[Path] = None
        if self.cache_dir:
            cache_path = self.cache_dir / f"sportsdataio_games_{season}.json"
            if cache_path.exists():
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
                return games_from_sportsdataio_payload(payload, season=season)
        payload = self._http_get(f"/scores/json/Games/{season}")
        if cache_path:
            cache_path.write_text(json.dumps(payload), encoding="utf-8")
        return games_from_sportsdataio_payload(payload, season=season)

    def available_seasons(self) -> List[int]:
        # SportsDataIO unterstützt typisch 2005..aktuelle Saison.
        # Wir konservativ einschränken.
        return list(range(2018, datetime.now().year + 1))
