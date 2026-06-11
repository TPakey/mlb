"""Reise-/Getaway-Day-Feasibility (P1-3 D1).

Flaggt **unrealistische Back-to-Backs**: ein Team, das an Kalendertag D in
Stadt A spielt und am Folgetag D+1 in Stadt B (A != B), ohne Off-Day dazwischen.
Solche "Getaway-Day"-Transfers gibt es im realen MLB-Plan reichlich — die Frage
ist nur, *welche* davon noch innerhalb dessen liegen, was reale Profi-Planer
jemals legen, und welche darüber hinausschießen.

Warum nicht "Nachtspiel → Tagspiel"?
------------------------------------
Die naheliegende Definition aus dem Review ("Nachtspiel → Tagspiel über mehrere
Zeitzonen") braucht **Spiel-Uhrzeiten** (day/night). Unser Produkt-Output — der
optimierte Plan — ist jedoch auf **Tagesebene** (keine zugewiesenen Anstoßzeiten;
``season.Game`` trägt nur ein Datum). Eine day/night-Prüfung wäre auf jedem
generierten Plan wirkungslos. Deshalb ist die **durchsetzbare** Feasibility-Regel
distanz- und zeitzonenbasiert; der day/night-Layer ist optional und greift nur,
wenn Uhrzeiten vorliegen (reale Pläne, Audit).

Datenbasierte Schwellen (gemessen, nicht behauptet)
---------------------------------------------------
Aus real 2024 + 2025 (``data/mlb_schedule_*.json``), über alle 30 Teams, für
konsekutive Transfers (gap = 1 Tag, kein Off-Day):

- längster Back-to-Back in den as-played-Plänen 2024/2025: **4164 km** (MIA↔SFG),
  **max 3 TZ-Hops**.
- KALIBRIER-KORREKTUR (2026-06-11, Assessment): Der publizierte **2026-Originalplan**
  (Retrosheet, Rating A) legt BOS→OAK (4223 km, 2×) und BOS→SFG (4328 km) als
  Back-to-Backs — die alte Schwelle 4200 war ein Zwei-Saison-Artefakt und wurde
  durch 2026 FALSIFIZIERT. Neue Schwelle 4350: deckt alle bis einschließlich 2026
  beobachteten Original-Back-to-Backs (max 4328) und blockiert weiterhin die nie
  gelegte Klasse ≥ 4392 (SEA↔MIA).
- ~30 % der konsekutiven Transfers sind ostwärts (Stunden-Verlust über Nacht),
  davon ~80 mit ≥2 TZ-Hops und bis 4164 km — also auch harte Turnarounds sind
  real, aber im oberen Rand.

Daraus die Klassifikation pro Transfer:

- ``exceeds_real_envelope`` — km über dem real beobachteten Maximum (> 4350 km)
  oder mehr TZ-Hops als in den USA überhaupt möglich (> 3). Das ist eine echte
  Feasibility-Verletzung: härter als alles, was reale Planer je gelegt haben.
- ``tight`` — innerhalb des realen Envelopes, aber im harten Rand-Bereich
  (ostwärts, ≥2 TZ-Hops, ≥ p95-Distanz). Kein Verstoß, aber ein
  Review-Hinweis ("tough turnaround").
- ``ok`` — unauffällig.

Alles deterministisch, ohne Zufall, auf dem ``season.Season``-Modell. Wird vom
Compliance-Report (``src/compliance.py``) konsumiert.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from .season import Season
from .distance import haversine_km
from .timezones import tz_offset_hours


# ====================================================================
# Schwellen — datenbasiert aus real 2024+2025 (siehe Modul-Docstring)
# ====================================================================

@dataclass(frozen=True)
class FeasibilityThresholds:
    """Schwellen für die Getaway-Feasibility-Klassifikation.

    Defaults sind aus den realen MLB-Plänen 2024/2025 abgeleitet. Wenn MLB-Ops
    abweichende Vorgaben liefert, hier zentral anpassen.
    """
    # Über dem real je beobachteten Back-to-Back-Maximum: as-played 2024/25 max
    # 4164; ORIGINALPLAN 2026 legt real bis 4328 (BOS→SFG) → Schwelle 4350
    # (deckt alles Beobachtete, blockiert die nie gelegte Klasse ≥ 4392 SEA↔MIA).
    # Historie: bis 2026-06-11 stand hier 4200 — durch den 2026-Originalplan
    # falsifiziert (Assessment-Befund; docs/ASSESSMENT_2026-06-11.md).
    max_real_consecutive_km: float = 4350.0
    # In den USA sind max. 3 Zeitzonen-Hops möglich; mehr ist physikalisch ausgeschlossen.
    max_tz_hops: int = 3
    # "tight"-Rand: p95 der realen konsekutiven Transfer-Distanz (~3000 km).
    tight_km: float = 3000.0
    # "tight" verlangt zusätzlich Ostrichtung (Stunden-Verlust) und mind. so viele Hops.
    tight_min_hops: int = 2


# Modul-Default, damit Aufrufer ohne eigene Konfiguration auskommen.
DEFAULT_THRESHOLDS = FeasibilityThresholds()


# ====================================================================
# Datentypen
# ====================================================================

@dataclass(frozen=True)
class GetawayTransition:
    """Ein Stadt-Wechsel eines Teams zwischen zwei aufeinanderfolgenden Spieltagen."""
    team: str
    from_city: str          # Team-ID des Heimteams am Abreise-Spielort
    to_city: str            # Team-ID des Heimteams am Ankunfts-Spielort
    depart_date: date       # letzter Spieltag in from_city vor dem Wechsel
    arrive_date: date       # erster Spieltag in to_city
    gap_days: int           # (arrive - depart).days; 1 = kein Off-Day dazwischen
    km: float
    tz_hops: int
    eastward: bool          # True = Richtung Osten (Offset steigt) → Stunden-Verlust über Nacht
    severity: str           # "ok" | "tight" | "exceeds_real_envelope"

    @property
    def is_violation(self) -> bool:
        return self.severity == "exceeds_real_envelope"

    @property
    def is_back_to_back(self) -> bool:
        return self.gap_days == 1


@dataclass(frozen=True)
class FeasibilityReport:
    by_team: Dict[str, List[GetawayTransition]]
    thresholds: FeasibilityThresholds = field(default_factory=lambda: DEFAULT_THRESHOLDS)

    # ---- aggregierte Sichten ----

    @property
    def all_transitions(self) -> List[GetawayTransition]:
        out: List[GetawayTransition] = []
        for ts in self.by_team.values():
            out.extend(ts)
        return out

    @property
    def violations(self) -> List[GetawayTransition]:
        """Transfers jenseits des realen MLB-Envelopes (echte Feasibility-Verstöße)."""
        return [t for t in self.all_transitions if t.severity == "exceeds_real_envelope"]

    @property
    def tight(self) -> List[GetawayTransition]:
        """Harte, aber real-konforme Turnarounds (Review-Hinweise, kein Verstoß)."""
        return [t for t in self.all_transitions if t.severity == "tight"]

    @property
    def ok(self) -> bool:
        return not self.violations

    @property
    def max_consecutive_km(self) -> float:
        b2b = [t.km for t in self.all_transitions if t.is_back_to_back]
        return max(b2b) if b2b else 0.0

    def summary(self) -> Dict[str, float]:
        b2b = [t for t in self.all_transitions if t.is_back_to_back]
        return {
            "n_transitions": len(self.all_transitions),
            "n_back_to_back": len(b2b),
            "n_violations": len(self.violations),
            "n_tight": len(self.tight),
            "max_consecutive_km": round(self.max_consecutive_km, 1),
        }


# ====================================================================
# Kernlogik
# ====================================================================

def _team_locations_by_day(season: Season, team_id: str) -> List[tuple]:
    """(date, city_team_id) je Spieltag des Teams, ein Eintrag pro Kalendertag.

    Die "Stadt" ist die Team-ID des Heimteams am jeweiligen Spielort (für ein
    Heimspiel also das Team selbst, für ein Auswärtsspiel der Gegner).
    Doubleheader (selber Tag, selber Ort) kollabieren zu einem Eintrag.
    """
    by_day: Dict[date, str] = {}
    for g in season.games:
        if not g.involves(team_id):
            continue
        # Erstes Spiel des Tages bestimmt den Ort (DH ist ohnehin gleicher Ort).
        if g.date not in by_day:
            by_day[g.date] = g.home
    return [(d, by_day[d]) for d in sorted(by_day)]


def _classify(km: float, tz_hops: int, eastward: bool,
              th: FeasibilityThresholds) -> str:
    if km > th.max_real_consecutive_km or tz_hops > th.max_tz_hops:
        return "exceeds_real_envelope"
    if eastward and tz_hops >= th.tight_min_hops and km >= th.tight_km:
        return "tight"
    return "ok"


def team_transitions(
    season: Season,
    team_id: str,
    teams_by_id: Dict,
    *,
    thresholds: FeasibilityThresholds = DEFAULT_THRESHOLDS,
    only_back_to_back: bool = True,
) -> List[GetawayTransition]:
    """Alle (optional: nur Back-to-Back-) Stadtwechsel eines Teams, klassifiziert.

    ``teams_by_id``: Mapping Team-ID -> Team (für lat/lon/timezone), z. B.
    ``data_loader.teams_by_id(load_teams())``.

    ``only_back_to_back=True`` (Default): nur Transfers ohne Off-Day dazwischen
    (gap = 1 Tag) — dort entsteht der Getaway-Day-Stress. Mit ``False`` werden
    auch Transfers mit Off-Day-Puffer aufgelistet (immer "ok").
    """
    locs = _team_locations_by_day(season, team_id)
    out: List[GetawayTransition] = []
    for (d0, c0), (d1, c1) in zip(locs, locs[1:]):
        if c0 == c1:
            continue
        gap = (d1 - d0).days
        if only_back_to_back and gap != 1:
            continue
        ta, tb = teams_by_id[c0], teams_by_id[c1]
        km = haversine_km(ta.lat, ta.lon, tb.lat, tb.lon)
        off0 = tz_offset_hours(ta.timezone, d1)
        off1 = tz_offset_hours(tb.timezone, d1)
        tz_hops = abs(off1 - off0)
        eastward = off1 > off0  # Ziel weiter östlich → höherer (weniger negativer) Offset
        severity = _classify(km, tz_hops, eastward, thresholds) if gap == 1 else "ok"
        out.append(GetawayTransition(
            team=team_id, from_city=c0, to_city=c1,
            depart_date=d0, arrive_date=d1, gap_days=gap,
            km=km, tz_hops=tz_hops, eastward=eastward, severity=severity,
        ))
    return out


def feasibility_report(
    season: Season,
    team_ids: List[str],
    teams_by_id: Optional[Dict] = None,
    *,
    thresholds: FeasibilityThresholds = DEFAULT_THRESHOLDS,
    only_back_to_back: bool = True,
) -> FeasibilityReport:
    """Getaway-Feasibility über alle gegebenen Teams.

    ``teams_by_id`` ist optional — fehlt es, werden die Stammdaten via
    ``data_loader.load_teams()`` geladen (Bequemlichkeit für CLI/Tests).
    """
    if teams_by_id is None:
        from .data_loader import load_teams, teams_by_id as _tbi
        teams_by_id = _tbi(load_teams())
    by_team = {
        t: team_transitions(season, t, teams_by_id,
                            thresholds=thresholds,
                            only_back_to_back=only_back_to_back)
        for t in team_ids
    }
    return FeasibilityReport(by_team=by_team, thresholds=thresholds)
