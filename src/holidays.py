"""Feiertags-/Marquee-Pins (P1-3).

MLB legt bewusst Wert darauf, dass an Schlüsseltagen das *richtige* Programm
läuft: am Saisonauftakt und an Nationalfeiertagen ein voller Slate, an
Marquee-Tagen die großen Rivalitäten. Dieses Modul macht diese Erwartung
**explizit, prüfbar und bewertbar** — als Pins (soll-erfüllt) und Incentives
(je besser erfüllt, desto höher der Score).

Zwei Pin-Arten (aus ``data/holiday_pins.json``):

- ``league_wide`` — an diesem Datum soll möglichst die ganze Liga spielen
  (voller 15-Spiele-Slate, alle 30 Teams aktiv). Beispiele: Jackie Robinson Day
  (15. April), Memorial Day, 4. Juli, Labor Day. Im realen Plan sind das
  verifiziert volle Slates (alle 30 Teams aktiv).
- ``marquee_incentive`` — an diesem Datum sind Marquee-/Rivalry-Matchups
  besonders wertvoll (Score steigt mit Anzahl/Stärke der Marquee-Spiele).
  Beispiel: Opening Day.

Die Marquee-Erkennung nutzt die bereits vorhandene TV-Slot-Konfiguration
(``data/tv_slots.json`` → ``tv_slots.TvSlotConfig.marquee_mult``), damit hier
keine Matchup-Daten dupliziert/erfunden werden.

Datumsberechnung deterministisch aus Regeln (fix / nth-weekday / opening_day).
Reines Reporting/Scoring — verändert keinen Plan. Wird vom Compliance-Report
(``src/compliance.py``) konsumiert.
"""
from __future__ import annotations

import calendar
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from .season import Season

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ====================================================================
# Datumsregeln
# ====================================================================

def nth_weekday(year: int, month: int, weekday: int, ordinal: int) -> date:
    """Datum des n-ten Wochentags eines Monats.

    ``weekday`` 0=Montag .. 6=Sonntag (wie ``date.weekday()``).
    ``ordinal`` 1 = erster, 2 = zweiter, ..., -1 = letzter.
    """
    days_in_month = calendar.monthrange(year, month)[1]
    matches = [
        d for d in range(1, days_in_month + 1)
        if date(year, month, d).weekday() == weekday
    ]
    if not matches:  # pragma: no cover - jeder Wochentag kommt jeden Monat vor
        raise ValueError(f"Kein Wochentag {weekday} in {year}-{month}")
    idx = ordinal - 1 if ordinal > 0 else ordinal
    return date(year, month, matches[idx])


def resolve_holiday_date(rule: dict, season: Season) -> Optional[date]:
    """Berechnet das konkrete Datum eines Feiertags für die Saison.

    Gibt ``None`` zurück, wenn das Datum nicht zu bestimmen ist (z. B.
    ``opening_day`` ohne Spiele).
    """
    year = season.season
    typ = rule.get("type")
    if typ == "fixed":
        return date(year, int(rule["month"]), int(rule["day"]))
    if typ == "nth_weekday":
        return nth_weekday(year, int(rule["month"]), int(rule["weekday"]),
                           int(rule["ordinal"]))
    if typ == "opening_day":
        if not season.games:
            return None
        return min(g.date for g in season.games)
    raise ValueError(f"Unbekannte Feiertagsregel: {rule!r}")


# ====================================================================
# Datentypen
# ====================================================================

@dataclass(frozen=True)
class Holiday:
    key: str
    name: str
    on_date: Optional[date]
    kind: str          # "league_wide" | "marquee_incentive"
    weight: float
    description: str


@dataclass(frozen=True)
class HolidayEvaluation:
    holiday: Holiday
    in_season: bool
    n_games: int
    teams_active: int
    n_marquee: int
    marquee_labels: List[str]
    score: float
    note: str

    @property
    def is_full_slate(self) -> bool:
        # Voller Slate = alle 30 Teams aktiv (15 Spiele).
        return self.teams_active >= 30


@dataclass(frozen=True)
class HolidayReport:
    evaluations: List[HolidayEvaluation]

    @property
    def total_score(self) -> float:
        return sum(e.score for e in self.evaluations)

    @property
    def in_season(self) -> List[HolidayEvaluation]:
        return [e for e in self.evaluations if e.in_season]

    @property
    def league_wide_gaps(self) -> List[HolidayEvaluation]:
        """league_wide-Feiertage in der Saison, die KEIN voller Slate sind."""
        return [
            e for e in self.evaluations
            if e.in_season and e.holiday.kind == "league_wide" and not e.is_full_slate
        ]

    def summary(self) -> Dict[str, float]:
        return {
            "n_holidays": len(self.evaluations),
            "n_in_season": len(self.in_season),
            "total_score": round(self.total_score, 2),
            "n_league_wide_gaps": len(self.league_wide_gaps),
            "total_marquee_on_holidays": sum(e.n_marquee for e in self.evaluations),
        }


# ====================================================================
# Laden + Auswerten
# ====================================================================

def load_holidays(season: Season, path: Optional[Path] = None) -> List[Holiday]:
    """Lädt die Pin-Definitionen und löst die Daten für die Saison auf."""
    path = path or (DATA_DIR / "holiday_pins.json")
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    out: List[Holiday] = []
    for h in raw["holidays"]:
        out.append(Holiday(
            key=h["key"],
            name=h["name"],
            on_date=resolve_holiday_date(h["rule"], season),
            kind=h["kind"],
            weight=float(h.get("weight", 1.0)),
            description=h.get("description", ""),
        ))
    return out


def _marquee_on(season: Season, day: date, marquee_fn) -> List[str]:
    """Labels der Marquee-Spiele an einem Tag (marquee_fn(home, away) > 1.0)."""
    labels: List[str] = []
    for g in season.games_on(day):
        if g.doubleheader_seq == 2:
            continue  # DH nur einmal zählen
        if marquee_fn(g.home, g.away) > 1.0:
            labels.append(f"{g.away}@{g.home}")
    return labels


def evaluate_holiday(season: Season, holiday: Holiday, marquee_fn) -> HolidayEvaluation:
    day = holiday.on_date
    in_season = bool(
        day is not None and season.games
        and min(g.date for g in season.games) <= day <= max(g.date for g in season.games)
    )
    if not in_season:
        return HolidayEvaluation(
            holiday=holiday, in_season=False, n_games=0, teams_active=0,
            n_marquee=0, marquee_labels=[], score=0.0,
            note="außerhalb der Saison" if day else "Datum unbestimmt",
        )

    games = [g for g in season.games_on(day) if g.doubleheader_seq != 2]
    teams_active = len({g.home for g in games} | {g.away for g in games})
    marquee_labels = _marquee_on(season, day, marquee_fn)
    n_marquee = len(marquee_labels)

    if holiday.kind == "league_wide":
        # Score skaliert mit dem Anteil aktiver Teams (1.0 bei vollem Slate).
        coverage = teams_active / 30.0
        score = holiday.weight * coverage
        note = (f"voller Slate ({teams_active}/30 Teams aktiv)"
                if teams_active >= 30
                else f"unvollständig: nur {teams_active}/30 Teams aktiv")
    else:  # marquee_incentive
        # Score skaliert mit Anzahl Marquee-Spiele (gedeckelt, damit ein Tag
        # nicht beliebig dominiert).
        score = holiday.weight * min(n_marquee, 4)
        note = (f"{n_marquee} Marquee-Matchup(s): {', '.join(marquee_labels)}"
                if n_marquee else "kein Marquee-Matchup")

    return HolidayEvaluation(
        holiday=holiday, in_season=True, n_games=len(games),
        teams_active=teams_active, n_marquee=n_marquee,
        marquee_labels=marquee_labels, score=round(score, 3), note=note,
    )


def holiday_report(
    season: Season,
    path: Optional[Path] = None,
    marquee_fn=None,
) -> HolidayReport:
    """Bewertet alle Feiertags-Pins gegen einen Plan.

    ``marquee_fn(home, away) -> float`` (>1.0 = Marquee). Fehlt es, wird die
    TV-Slot-Konfiguration (``tv_slots.TvSlotConfig``) geladen.
    """
    if marquee_fn is None:
        from .tv_slots import TvSlotConfig
        cfg = TvSlotConfig.load()
        marquee_fn = cfg.marquee_mult
    holidays = load_holidays(season, path)
    return HolidayReport(
        evaluations=[evaluate_holiday(season, h, marquee_fn) for h in holidays]
    )
