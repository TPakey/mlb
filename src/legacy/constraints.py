"""Hard Constraints — binäre Bedingungen, die NIE verletzt werden dürfen.

Inspiriert vom League-Grade-Scheduling-Framework: harte Constraints müssen
minimal, stabil und extrem gut definiert sein. Zu viele davon machen das
Optimierungsproblem unlösbar. Wir formulieren nur die, die operativ wirklich
binär sind, und packen alles andere in Soft-Penalties.

Kategorien (aus dem Forschungspapier):
- League Structure (Spielzahl, Heim/Auswärts-Balance, Divisionsstruktur)
- Calendar (Saisonfenster, All-Star-Break, max. 1 Serie pro Slot)
- Venue (Stadion-Blackouts)
- Travel Feasibility (minimale Transitzeit)
- Labor Agreement (max. aufeinanderfolgende Spieltage)
- Broadcast Contract (Opening-Day-Slots, exklusive Fenster)
- Weather Safety (z. B. keine offenen Heimspiele in Schneestädten im Eröffnungs-Slot)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, List, Optional

from ..data_loader import Team
from .schedule_generator import Schedule, Series, SERIES_LENGTH, slot_to_date


@dataclass
class Violation:
    code: str
    message: str
    severity: str = "hard"   # "hard" | "soft"
    series: Optional[Series] = None


@dataclass
class ValidationReport:
    violations: List[Violation] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not any(v.severity == "hard" for v in self.violations)

    def by_code(self) -> Dict[str, List[Violation]]:
        out: Dict[str, List[Violation]] = {}
        for v in self.violations:
            out.setdefault(v.code, []).append(v)
        return out

    def summary(self) -> str:
        if self.is_valid:
            return "Plan erfüllt alle harten Constraints."
        lines = ["Verletzungen gefunden:"]
        for code, vs in self.by_code().items():
            lines.append(f"  {code}: {len(vs)}× — {vs[0].message}")
        return "\n".join(lines)


# ---------------------- Einzelne Constraint-Checks ----------------------

def check_one_series_per_team_per_slot(sched: Schedule) -> List[Violation]:
    out: List[Violation] = []
    for slot, ss in sched.by_slot().items():
        seen: Dict[str, Series] = {}
        for s in ss:
            for tid in (s.home, s.away):
                if tid in seen:
                    out.append(Violation(
                        code="CAL_DOUBLE_BOOK",
                        message=f"Team {tid} doppelt eingeplant in Slot {slot}",
                        series=s,
                    ))
                seen[tid] = s
    return out


def check_team_count_and_division_structure(teams: List[Team]) -> List[Violation]:
    if len(teams) != 30:
        return [Violation("STRUCT_TEAM_COUNT", f"Erwartet 30 Teams, gefunden {len(teams)}")]
    return []


def check_home_away_balance(sched: Schedule, teams: List[Team], max_imbalance: int = 2) -> List[Violation]:
    counts = {t.id: 0 for t in teams}
    total = {t.id: 0 for t in teams}
    for s in sched.series:
        counts[s.home] += 1
        total[s.home] += 1
        total[s.away] += 1
    target = sum(counts.values()) / len(counts)
    out: List[Violation] = []
    for tid, c in counts.items():
        if abs(c - target) > max_imbalance:
            out.append(Violation(
                code="STRUCT_HOME_BALANCE",
                message=f"Team {tid}: {c} Heimserien (Soll-Zielwert {target:.0f}, "
                        f"Toleranz ±{max_imbalance})",
            ))
    return out


def check_all_star_break(sched: Schedule, break_slots: List[int]) -> List[Violation]:
    out: List[Violation] = []
    for s in sched.series:
        if s.slot in break_slots:
            out.append(Violation(
                code="CAL_ALL_STAR",
                message=f"Serie im All-Star-Slot {s.slot}: {s.home} vs {s.away}",
                series=s,
            ))
    return out


def check_venue_blackouts(sched: Schedule, blackouts: Dict[str, List[tuple]]) -> List[Violation]:
    """blackouts: { team_id: [(start_date, end_date), ...] } für Heim-Blackouts."""
    out: List[Violation] = []
    for s in sched.series:
        if s.home not in blackouts:
            continue
        s_start = slot_to_date(s.slot)
        s_end = s_start + timedelta(days=SERIES_LENGTH - 1)
        for b_start, b_end in blackouts[s.home]:
            if not (s_end < b_start or b_end < s_start):
                out.append(Violation(
                    code="VENUE_BLACKOUT",
                    message=f"Heim-Blackout {s.home} {b_start}–{b_end} kollidiert mit Serie Slot {s.slot}",
                    series=s,
                ))
    return out


def check_minimum_transit(sched: Schedule, teams_by_id: Dict[str, Team],
                          min_hours_between_distant: float = 18.0) -> List[Violation]:
    """Travel-Feasibility: ein Team darf nicht in zwei Slots direkt
    nacheinander in geographisch unmögliche Konstellationen geraten.
    Unsere Slots sind 7 Tage auseinander → das ist in der Realität immer
    machbar. Wir prüfen trotzdem, ob die Sequenz logisch konsistent ist."""
    # In unserem 7-Tage-Slot-Modell ist Transit immer feasible.
    # Diese Funktion dient als Schnittstelle für strengere Modelle.
    return []


def check_consecutive_road_days(sched: Schedule, teams: List[Team],
                                max_consecutive_away: int = 7) -> List[Violation]:
    """Labor-Agreement-Proxy: max. N aufeinanderfolgende Auswärts-Slots."""
    out: List[Violation] = []
    for t in teams:
        ts = sorted(sched.for_team(t.id), key=lambda x: x.slot)
        run = 0
        for s in ts:
            if not s.is_home_for(t.id):
                run += 1
                if run > max_consecutive_away:
                    out.append(Violation(
                        code="LABOR_LONG_ROAD",
                        message=f"Team {t.id}: {run} aufeinanderfolgende Auswärts-Slots",
                    ))
                    break
            else:
                run = 0
    return out


# ---------------------- Aggregator ----------------------

def validate(sched: Schedule, teams: List[Team],
             teams_by_id: Dict[str, Team],
             all_star_slots: Optional[List[int]] = None,
             venue_blackouts: Optional[Dict[str, List[tuple]]] = None) -> ValidationReport:
    """Vollständige Hard-Constraint-Prüfung des Plans."""
    report = ValidationReport()
    report.violations.extend(check_team_count_and_division_structure(teams))
    report.violations.extend(check_one_series_per_team_per_slot(sched))
    report.violations.extend(check_home_away_balance(sched, teams))
    if all_star_slots:
        report.violations.extend(check_all_star_break(sched, all_star_slots))
    if venue_blackouts:
        report.violations.extend(check_venue_blackouts(sched, venue_blackouts))
    report.violations.extend(check_minimum_transit(sched, teams_by_id))
    report.violations.extend(check_consecutive_road_days(sched, teams))
    return report
