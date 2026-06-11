"""Local-Event-Friction- und Stadium-Booking-Layer (Sprint 2.3 Phase 2).

Liest `data/local_events.json` und liefert zwei Sichten auf die Daten:

1. **Stadium-Bookings** als harte Constraints fuer den Generator. Konzerte und
   andere Drittnutzungen des MLB-Stadions blockieren das Heimspiel komplett.
   Diese werden via `generator.GeneratorConfig.home_blackout_days` an den
   CP-SAT-Solver gegeben (selbe Infrastruktur wie Sprint 2.2-Strategie B).

2. **Local-Event-Friction-Score** als weiche Pareto-Achse. Pro Plan summieren
   wir die Severity der Heimspiele in Konflikt-Fenstern. Stadium-Bookings
   selbst sind hier AUSGESCHLOSSEN (sonst doppelte Strafe — sie sind ja
   bereits hart erzwungen).

Konsumenten:
- `generator.generate()` ueber `home_blackout_days` (Sprint 2.2-Mechanik)
- `pareto.py` (Sprint 2.3 Phase 4) ueber `event_friction_score()`
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from .season import Season


DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Severity 1..5; Stadium-Bookings sind per Definition >= 4 (harte Sperre)
STADIUM_BOOKING_CATEGORY = "stadium_booking"


@dataclass(frozen=True)
class LocalEvent:
    """Ein Event aus `data/local_events.json`."""
    city: str
    team_ids: Tuple[str, ...]
    name: str
    start_date: date
    end_date: date
    severity: int                   # 1..5
    category: str
    source: str = ""
    note: str = ""

    def __post_init__(self):
        if self.end_date < self.start_date:
            raise ValueError(
                f"end_date {self.end_date} liegt vor start_date {self.start_date}"
            )
        if not 1 <= self.severity <= 5:
            raise ValueError(f"severity muss in 1..5 sein, ist {self.severity}")

    def affects_team(self, team_id: str) -> bool:
        return team_id in self.team_ids

    def covers_date(self, d: date) -> bool:
        return self.start_date <= d <= self.end_date

    def is_stadium_booking(self) -> bool:
        return self.category == STADIUM_BOOKING_CATEGORY


# ====================================================================
# Loader
# ====================================================================

def load_local_events(path: Optional[Path] = None) -> List[LocalEvent]:
    """Laedt alle Events aus `data/local_events.json`.

    Liefert eine deterministische Liste in der Reihenfolge der JSON-Eintraege.
    """
    import warnings as _warnings
    path = path or (DATA_DIR / "local_events.json")
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)
    out: List[LocalEvent] = []
    # Audit A13 (Sprint A-4): pro-Event-Robustheit — ein fehlerhaft gepflegter
    # Event-Eintrag soll nicht den gesamten Generator-Lauf killen, sondern als
    # Warning gemeldet und uebersprungen werden.
    for idx, e in enumerate(raw.get("events", [])):
        try:
            out.append(LocalEvent(
                city=e["city"],
                team_ids=tuple(e["team_ids"]),
                name=e["name"],
                start_date=date.fromisoformat(e["start_date"]),
                end_date=date.fromisoformat(e["end_date"]),
                severity=int(e["severity"]),
                category=e.get("category", "festival"),
                source=e.get("source", ""),
                note=e.get("note", ""),
            ))
        except Exception as exc:
            _warnings.warn(
                f"local_events.json[{idx}]: Eintrag '{e.get('name', '?')}' "
                f"uebersprungen ({exc!r}).",
                RuntimeWarning,
                stacklevel=2,
            )
    return out


# ====================================================================
# Stadium-Bookings -> home_blackout_days
# ====================================================================

def stadium_bookings_to_blackout_days(
    events: List[LocalEvent],
    season_start: date,
    season_end: date,
) -> Dict[str, FrozenSet[int]]:
    """Konvertiert Stadium-Booking-Events in `home_blackout_days` fuer den
    Generator. Tag-Indizes sind relativ zu `season_start`.

    Pro Heimteam ein FrozenSet der Tag-Indizes, an denen das Stadion belegt
    ist und somit kein MLB-Heimspiel stattfinden darf.

    Events ausserhalb des Saisonfensters werden ignoriert (z. B. NYC-Marathon
    am 01.11.2026 nach Saisonende).
    """
    blackout: Dict[str, Set[int]] = {}
    for e in events:
        if not e.is_stadium_booking():
            continue
        # Schnitt mit Saisonfenster
        eff_start = max(e.start_date, season_start)
        eff_end = min(e.end_date, season_end)
        if eff_end < eff_start:
            continue   # liegt ausserhalb der Saison
        d = eff_start
        while d <= eff_end:
            day_idx = (d - season_start).days
            for tid in e.team_ids:
                blackout.setdefault(tid, set()).add(day_idx)
            d += timedelta(days=1)
    return {tid: frozenset(days) for tid, days in blackout.items()}


# ====================================================================
# Harter Venue-Belegungskalender — Verifikation (Sprint 4)
# ====================================================================

@dataclass(frozen=True)
class VenueConflict:
    """Ein Heimspiel, das auf einen Stadion-Belegungstag fällt (harter Konflikt)."""
    team_id: str
    date: date
    event_name: str


def venue_conflicts(
    season: Season,
    events: List[LocalEvent],
) -> List[VenueConflict]:
    """Prüft den Plan gegen den **harten** Venue-Belegungskalender.

    Ein Konflikt liegt vor, wenn ein **Heimspiel** auf einen Tag fällt, an dem
    das Stadion durch eine Drittnutzung (``stadium_booking``) belegt ist. Das ist
    ein harter Verstoß: an einem belegten Tag kann physisch kein MLB-Heimspiel
    stattfinden.

    Gegenstück zur *Durchsetzung* (``stadium_bookings_to_blackout_days`` →
    ``GeneratorConfig.home_blackout_days``, vom CP-SAT-Generator und der
    SA respektiert): diese Funktion **verifiziert** einen fertigen Plan.
    Datenunabhängig — funktioniert mit jedem (auch echten MLB-)Belegungskalender
    im selben Event-Schema.

    Deterministisch: Konflikte nach (Datum, Team) sortiert.
    """
    # Index: pro Heimteam {tag_datum: event_name} der Stadion-Belegungen.
    booked: Dict[str, Dict[date, str]] = {}
    for e in events:
        if not e.is_stadium_booking():
            continue
        for tid in e.team_ids:
            day_map = booked.setdefault(tid, {})
            d = e.start_date
            while d <= e.end_date:
                day_map.setdefault(d, e.name)
                d += timedelta(days=1)
    out: List[VenueConflict] = []
    for g in season.games:
        day_map = booked.get(g.home)
        if day_map and g.date in day_map:
            out.append(VenueConflict(team_id=g.home, date=g.date,
                                     event_name=day_map[g.date]))
    out.sort(key=lambda c: (c.date, c.team_id))
    return out


# ====================================================================
# Local-Event-Friction-Score (Sprint 2.3 Phase 4)
# ====================================================================

@dataclass(frozen=True)
class EventFrictionReport:
    """Score-Bundle-Komponente: aggregierter Friction-Score plus Aufschluesselung."""
    total_score: float
    by_team: Dict[str, float]
    by_event_category: Dict[str, float]


def event_friction_score(
    season: Season,
    events: List[LocalEvent],
    exclude_stadium_bookings: bool = True,
) -> EventFrictionReport:
    """Berechnet den Local-Event-Friction-Score fuer einen Plan.

    Logik:
    - Pro Heimspiel: prueft alle Events, die diese Stadt/dieses Team an diesem
      Datum treffen, summiert deren `severity`.
    - Stadium-Bookings werden per Default exkludiert (sie sind harte Constraints,
      sonst doppelte Strafe).

    `total_score` ist die Summe ueber alle Heimspiele.
    `by_team` schluesselt nach Heimteam auf.
    `by_event_category` schluesselt nach Event-Kategorie auf.
    """
    by_team: Dict[str, float] = {}
    by_cat: Dict[str, float] = {}
    total = 0.0

    # Index: pro Team eine Liste der relevanten Events (effizienter Lookup)
    events_by_team: Dict[str, List[LocalEvent]] = {}
    for e in events:
        if exclude_stadium_bookings and e.is_stadium_booking():
            continue
        for tid in e.team_ids:
            events_by_team.setdefault(tid, []).append(e)

    for g in season.games:
        team_events = events_by_team.get(g.home, [])
        for e in team_events:
            if e.covers_date(g.date):
                total += e.severity
                by_team[g.home] = by_team.get(g.home, 0.0) + e.severity
                by_cat[e.category] = by_cat.get(e.category, 0.0) + e.severity

    return EventFrictionReport(
        total_score=total,
        by_team=by_team,
        by_event_category=by_cat,
    )
