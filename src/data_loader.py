"""Lädt und validiert die Stammdaten.

Enthält alle Funktionen, um Team-, Distanz- und Soft-Factor-Daten konsistent
in den Speicher zu laden und einfache Sanity-Checks zu fahren.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class Team:
    id: str
    name: str
    league: str            # "AL" | "NL"
    division: str          # "East" | "Central" | "West"
    stadium: str
    city: str
    state: str
    lat: float
    lon: float
    timezone: str
    roof: str              # "open" | "retractable" | "dome"
    cold_weather: bool
    notes: str

    @property
    def division_key(self) -> str:
        return f"{self.league}-{self.division}"


@dataclass(frozen=True)
class SoftEvent:
    city: str
    team_ids: tuple
    name: str
    start: date
    end: date
    severity: int          # 1 (mild) .. 5 (massiv)
    reason: str


_TEAM_REQUIRED_FIELDS: tuple = (
    "id", "name", "league", "division", "stadium", "city", "state",
    "lat", "lon", "timezone", "roof", "cold_weather", "notes",
)


def _validate_team_record(idx: int, t: dict) -> None:
    """Audit A24 (Sprint A-3): klare Fehlermeldungen statt nichtssagender
    TypeErrors aus `Team(**t)` bei fehlenden/falschen Feldern."""
    if not isinstance(t, dict):
        raise ValueError(f"teams.json[{idx}]: erwartet Objekt, fand {type(t).__name__}")
    missing = [f for f in _TEAM_REQUIRED_FIELDS if f not in t]
    if missing:
        raise ValueError(
            f"teams.json[{idx}] (id={t.get('id', '?')}): "
            f"fehlende Felder: {missing}. Erwartet: {_TEAM_REQUIRED_FIELDS}"
        )
    if t["league"] not in ("AL", "NL"):
        raise ValueError(
            f"teams.json[{idx}] id={t.get('id')}: league={t['league']!r} "
            f"ungültig (erwartet 'AL' oder 'NL')"
        )
    if t["division"] not in ("East", "Central", "West"):
        raise ValueError(
            f"teams.json[{idx}] id={t.get('id')}: division={t['division']!r} "
            f"ungültig (erwartet 'East', 'Central' oder 'West')"
        )
    try:
        lat, lon = float(t["lat"]), float(t["lon"])
    except (TypeError, ValueError):
        raise ValueError(
            f"teams.json[{idx}] id={t.get('id')}: lat/lon nicht numerisch"
        )
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        raise ValueError(
            f"teams.json[{idx}] id={t.get('id')}: lat={lat}, lon={lon} "
            f"ausserhalb plausibler Wertebereiche"
        )
    if t["roof"] not in ("open", "retractable", "dome"):
        raise ValueError(
            f"teams.json[{idx}] id={t.get('id')}: roof={t['roof']!r} ungültig "
            f"(erwartet 'open', 'retractable' oder 'dome')"
        )


def load_teams(path: Optional[Path] = None) -> List[Team]:
    path = path or (DATA_DIR / "teams.json")
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)
    if "teams" not in raw or not isinstance(raw["teams"], list):
        raise ValueError(
            f"teams.json muss ein Objekt mit Liste unter 'teams' enthalten "
            f"(Datei: {path})"
        )
    for idx, t in enumerate(raw["teams"]):
        _validate_team_record(idx, t)
    teams = [Team(**t) for t in raw["teams"]]
    _validate_teams(teams)
    return teams


def load_soft_factors(path: Optional[Path] = None) -> dict:
    path = path or (DATA_DIR / "soft_factors.json")
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)
    raw["events"] = [
        SoftEvent(
            city=e["city"],
            team_ids=tuple(e["team_ids"]),
            name=e["name"],
            start=date.fromisoformat(e["start"]),
            end=date.fromisoformat(e["end"]),
            severity=int(e["severity"]),
            reason=e.get("reason", ""),
        )
        for e in raw["events"]
    ]
    return raw


def teams_by_id(teams: List[Team]) -> Dict[str, Team]:
    return {t.id: t for t in teams}


def _validate_teams(teams: List[Team]) -> None:
    if len(teams) != 30:
        raise ValueError(f"Erwartet 30 Teams, gefunden: {len(teams)}")
    div_counts: Dict[str, int] = {}
    for t in teams:
        div_counts[t.division_key] = div_counts.get(t.division_key, 0) + 1
    for k, n in div_counts.items():
        if n != 5:
            raise ValueError(f"Division {k} hat {n} Teams (erwartet 5)")
    ids = {t.id for t in teams}
    if len(ids) != 30:
        raise ValueError("Duplizierte Team-IDs gefunden")

    # N10 (Sprint 2.11) + A15 (Sprint A-3): Timezone gegen die unterstützten
    # Zonen validieren. Seit dem Auszug nach `src.timezones` ist der Import
    # zykluskontrolliert; der frühere Lazy-Import ist nicht mehr nötig.
    from .timezones import TIMEZONE_OFFSET
    unknown = sorted({t.timezone for t in teams if t.timezone not in TIMEZONE_OFFSET})
    if unknown:
        raise ValueError(
            f"Unbekannte Timezone(s) in teams.json: {unknown}. "
            f"Unterstützt: {sorted(TIMEZONE_OFFSET)}. Ergänze den Offset in "
            f"src/timezones.py::TIMEZONE_OFFSET (seit Audit A15 dort, nicht mehr "
            f"in distance.py), sonst rechnet tz_offset_hours mit Fallback-Offset 0."
        )
