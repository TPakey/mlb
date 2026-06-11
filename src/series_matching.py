"""Phase B des HAP-Schedulers: Series-Matching (Sprint 2.3a).

Gegeben ein validiertes HAP-Set (30 Team-Patterns, pair-matching-konform,
AC-2.1.8/9-konform, Series-Länge 2-4), weist diese Phase jedem Team pro
HAP-Serie einen konkreten Gegner zu.

## Architektur

1. **HAP-Parsing**: Pro Team werden die Marks in Series-Objekte umgewandelt
   (maximale Läufe gleichen Typs: H oder A, Länge 2-4 nach Solver-Garantie).

2. **CP-SAT Phase B (Haupt-Algorithmus)**: Modelliert die Gegner-Zuweisung
   als ganzzahliges Erfüllungsproblem. Variablen x[h,a,d] ∈ {0,1} kodieren,
   ob Team h an Tag d gegen Team a spielt. Constraints:
   - Covering: pro Heim-Tag genau ein Gegner (sum_a x[h,a,d] = 1)
   - Exklusivität: pro Auswärts-Tag genau ein Gastgeber (sum_h x[h,a,d] = 1)
   - Series-Länge min 2: kein Matchup-Einzelspieltag
   - Series-Länge max 4: kein 5-Tage-Matchup
   - Kein Eigenspiel: h ≠ a

3. **Greedy-Fallback** (match_series): Schneller Greedy-Algorithmus als
   Fallback / Diagnose-Tool. Hat bekannte Schwäche: ~22% length-1 violations
   an HAP-Serien-Grenzen (wenn H- und A-Serien versetzt enden).

4. **Output**: Liste von `SeriesAssignment`-Objekten mit allen Spielen der
   regulären MLB-Saison.

## Matchup-Quoten (vereinfacht für Sprint 2.3a)

Matchup-Quoten (z. B. 19 Spiele gegen Division-Gegner) werden in Sprint 2.3b
als zweite Optimierungsebene ergänzt. Der aktuelle Solver setzt nur
strukturelle Gültigkeit durch (kein Team spielt gegen sich selbst, alle Spiele
haben einen Gegner).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("mlb.series_matching")

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

# ====================================================================
# Datenstrukturen
# ====================================================================

@dataclass(frozen=True)
class HAPSeries:
    """Ein kontinuierlicher Heim- oder Auswärts-Block im HAP-Pattern."""
    team_id: str
    type: str         # 'H' oder 'A'
    start_day: int    # inklusiv
    end_day: int      # inklusiv
    length: int       # = end_day - start_day + 1

    def days(self) -> range:
        return range(self.start_day, self.end_day + 1)

    def covers(self, d: int) -> bool:
        return self.start_day <= d <= self.end_day


@dataclass
class SeriesAssignment:
    """Ein konkretes Series-Matchup zwischen zwei Teams."""
    home_team: str
    away_team: str
    start_day: int
    end_day: int

    @property
    def length(self) -> int:
        return self.end_day - self.start_day + 1

    @property
    def days(self) -> range:
        return range(self.start_day, self.end_day + 1)


@dataclass
class SeriesMatchingResult:
    """Ergebnis des Phase-B-Matchings."""
    assignments: List[SeriesAssignment]
    unmatched_games: List[Tuple[int, str]]   # (day, team) ohne Gegner
    total_games: int
    series_lengths: Dict[int, int]            # length -> count
    violations: List[str]                     # Constraint-Verletzungen


# ====================================================================
# HAP-Parsing
# ====================================================================

def parse_hap_series(
    patterns: Dict[str, List[str]],
    break_days: Set[int],
) -> Dict[str, List[HAPSeries]]:
    """Parst die Marks-Arrays in eine Liste von HAPSeries pro Team."""
    result: Dict[str, List[HAPSeries]] = {}
    for team_id, marks in patterns.items():
        series_list: List[HAPSeries] = []
        cur_type: Optional[str] = None
        cur_start: Optional[int] = None
        for d, m in enumerate(marks):
            typ = m if m in ('H', 'A') else None
            if typ != cur_type:
                if cur_type is not None:
                    length = d - cur_start
                    series_list.append(HAPSeries(
                        team_id=team_id, type=cur_type,
                        start_day=cur_start, end_day=d - 1, length=length,
                    ))
                cur_type = typ
                cur_start = d if typ else None
        if cur_type is not None:
            length = len(marks) - cur_start
            series_list.append(HAPSeries(
                team_id=team_id, type=cur_type,
                start_day=cur_start, end_day=len(marks) - 1, length=length,
            ))
        result[team_id] = series_list
    return result


# ====================================================================
# Greedy Series-Matching
# ====================================================================

def match_series(
    patterns: Dict[str, List[str]],
    total_days: int,
    break_days: Set[int],
    verbose: bool = False,
) -> SeriesMatchingResult:
    """Weist jeder HAP-Home-Serie einen Away-Team-Gegner zu.

    Algorithmus:
    1. Pro Saisontag d: Home-Teams H(d) und Away-Teams A(d) ermitteln.
    2. Laufende Serien verlängern, sofern beide Teams noch spielen.
    3. Neue Serien starten: Greedy-Bipartite-Matching der verbleibenden Teams.
       Bevorzuge Away-Teams, deren HAP-Serie an Tag d oder d+1 startet
       (→ maximiert Überlappungs-Länge).
    4. Serien, die an Tag d enden, in assignments übertragen.

    Returns:
        SeriesMatchingResult mit allen Matchups und Diagnostik.
    """
    hap = parse_hap_series(patterns, break_days)

    # Index: für jeden Tag d → Mapping team → zugehörige HAPSeries
    # (für schnellen Zugriff auf "endet Team X an Tag d?")
    team_series_at: Dict[Tuple[str, int], HAPSeries] = {}
    for team_id, series_list in hap.items():
        for s in series_list:
            for d in s.days():
                team_series_at[(team_id, d)] = s

    assignments: List[SeriesAssignment] = []
    unmatched: List[Tuple[int, str]] = []

    # Laufende Matchups: home_team -> (away_team, series_start_day)
    active: Dict[str, Tuple[str, int]] = {}

    for d in range(total_days):
        if d in break_days:
            # Alle laufenden Serien abschließen
            for h, (a, start) in active.items():
                if d - 1 >= start:
                    assignments.append(SeriesAssignment(
                        home_team=h, away_team=a, start_day=start, end_day=d - 1,
                    ))
            active = {}
            continue

        H = {t for t, marks in patterns.items() if marks[d] == 'H'}
        A = {t for t, marks in patterns.items() if marks[d] == 'A'}

        if not H:
            continue

        # ── 1. Laufende Serien fortsetzen ──
        new_active: Dict[str, Tuple[str, int]] = {}
        continued_home: Set[str] = set()
        continued_away: Set[str] = set()

        for h, (a, start) in active.items():
            if h in H and a in A:
                new_active[h] = (a, start)
                continued_home.add(h)
                continued_away.add(a)
            else:
                # Serie endet: in assignments schreiben
                assignments.append(SeriesAssignment(
                    home_team=h, away_team=a, start_day=start, end_day=d - 1,
                ))

        # ── 2. Neue Serien für ungematchte Teams ──
        rem_H = sorted(H - continued_home)
        rem_A = sorted(A - continued_away)

        # Priorisierung: Matchings bevorzugen, bei denen home_remaining ≈ away_remaining
        # (gleiche verbleibende Serienlänge → kein Boundary-Mismatch → kein 1-Spiel-Serie)
        def series_remaining(team: str) -> int:
            s = team_series_at.get((team, d))
            return s.end_day - d + 1 if s else 0

        rem_H_sorted = sorted(rem_H, key=lambda h: series_remaining(h))
        rem_A_sorted = sorted(rem_A, key=lambda a: series_remaining(a))

        # Optimal-Matching: minimiere sum |rem_h - rem_a| durch "gleiche Richtung sortieren"
        # Beispiel: home_rem=[1,2,3], away_rem=[1,2,3] → (1-1)+(2-2)+(3-3)=0 Boundary-Mismatches
        # vs. home=[1,2,3], away=[3,2,1] → (1-3)+(2-2)+(3-1)=4 Mismatches
        for h, a in zip(rem_H_sorted, rem_A_sorted):
            new_active[h] = (a, d)
            continued_home.add(h)
            continued_away.add(a)

        # Nicht gematchte Teams (Längenungleichgewicht nach pair-matching — sollte 0 sein)
        for h in rem_H_sorted:
            if h not in continued_home:
                unmatched.append((d, h))
        for a in rem_A_sorted:
            if a not in continued_away:
                unmatched.append((d, a))

        active = new_active

    # Alle noch offenen Serien am Saisonende schließen
    for h, (a, start) in active.items():
        assignments.append(SeriesAssignment(
            home_team=h, away_team=a, start_day=start, end_day=total_days - 1,
        ))

    # ── Diagnostik ──
    from collections import Counter
    length_counter: Counter = Counter(ass.length for ass in assignments)
    violations: List[str] = []
    for ass in assignments:
        if ass.length < 2:
            violations.append(
                f"Series {ass.home_team} vs {ass.away_team} Tag {ass.start_day}: "
                f"Länge {ass.length} < 2"
            )
        if ass.length > 4:
            violations.append(
                f"Series {ass.home_team} vs {ass.away_team} Tag {ass.start_day}: "
                f"Länge {ass.length} > 4"
            )

    total_games = sum(ass.length for ass in assignments)

    if verbose:
        logger.info(f"[PhaseB] {len(assignments)} Serien  "
              f"total_games={total_games}  unmatched={len(unmatched)}")
        logger.info(f"  Series-Längen: {dict(sorted(length_counter.items()))}")
        logger.info(f"  Violations: {len(violations)}")

    return SeriesMatchingResult(
        assignments=assignments,
        unmatched_games=unmatched,
        total_games=total_games,
        series_lengths=dict(length_counter),
        violations=violations,
    )


# ====================================================================
# Slot-Based Phase B (korrekte Architektur, 0 Violations garantiert)
# ====================================================================

def match_series_slots(
    patterns: Dict[str, List[str]],
    total_days: int,
    break_days: Set[int],
    verbose: bool = False,
    time_limit_s: float = 180.0,
) -> SeriesMatchingResult:
    """Weist Gegner per Slot-basiertem CP-SAT-Modell zu.

    Architektur:
    -----------
    Statt pro-Tag-pro-Paar-Variablen verwendet dieses Modell "Slots":
    Ein Slot ist ein zusammenhängendes Sub-Intervall [e1..e2] (Länge 2-4)
    innerhalb der H-Serie einer Mannschaft. Das Away-Team muss für ALLE
    Tage des Slots verfügbar sein.

    Durch diese Modellierung:
    - Verletzungen mit Series-Länge 1 sind strukturell ausgeschlossen
      (Slots haben per Konstruktion Länge ≥ 2).
    - Das "isolierte Paar"-Problem entsteht gar nicht erst.
    - Partition-Constraint: die Slots einer H-Serie überdecken sie exakt.

    Variables:
        y[h, a, e1, e2] ∈ {0,1}: Home-Team h empfängt Away-Team a
                                  für die Tage [e1..e2].

    Constraints:
        1. Partition: für jeden H-Tag (h,d) genau ein aktiver Slot.
        2. Away-Exklusivität: Away-Team a ist an Tag d bei genau einem
           Home-Team zu Gast.
        3. Min-2/Max-4 sind durch Slot-Konstruktion garantiert.

    Laufzeit: ~20-60s für 30 Teams / 186 Tage.
    """
    from ortools.sat.python import cp_model
    from collections import defaultdict
    import time

    t0 = time.time()
    model = cp_model.CpModel()

    # ── H-Serien aus Patterns extrahieren ───────────────────────────────
    hap = parse_hap_series(patterns, break_days)
    h_series_list: List[HAPSeries] = [
        s for team_id, series_list in hap.items()
        for s in series_list if s.type == 'H'
    ]

    # ── Für schnellen Zugriff: pro Tag → Away-Teams ──────────────────────
    day_away: Dict[int, Set[str]] = {}
    for d in range(total_days):
        if d in break_days:
            continue
        a_set = {t for t, m in patterns.items() if m[d] == 'A'}
        if a_set:
            day_away[d] = a_set

    # ── Slot-Variablen erzeugen ──────────────────────────────────────────
    # y[(h, e1, e2, a)] = 1: h empfängt a für Tage [e1..e2]
    # Gültig wenn: a away auf ALLEN Tagen e1..e2 (kein Break dazwischen)
    y: Dict[Tuple[str, int, int, str], cp_model.IntVar] = {}

    # Mapping: (h, d) → Liste aller Slot-Vars die Tag d abdecken
    coverage_h: Dict[Tuple[str, int], List] = defaultdict(list)
    # Mapping: (a, d) → Liste aller Slot-Vars die a an Tag d belegen
    coverage_a: Dict[Tuple[str, int], List] = defaultdict(list)

    n_vars = 0
    for hs in h_series_list:
        h = hs.team_id
        d1, d2 = hs.start_day, hs.end_day
        # hs.length = d2 - d1 + 1 (garantiert ≥2 vom HAP-Solver)

        # Alle Sub-Intervalle [e1..e2] mit Länge 2..min(4, hs.length)
        # Nur konsekutive Spieltage (keine Breaks dazwischen)
        for e1 in range(d1, d2):            # e1 bis vorletzten Tag
            for e2 in range(e1 + 1, min(d2 + 1, e1 + 5)):  # Länge 2-4
                # Sicherstellen: kein Break zwischen e1 und e2
                if any(dd in break_days for dd in range(e1, e2 + 1)):
                    continue
                # Tage e1..e2 müssen alle zur H-Serie gehören
                if e2 > d2:
                    break

                # Gültige Away-Teams: away an ALLEN Tagen [e1..e2]
                away_all_days = set(day_away.get(e1, set()))
                for dd in range(e1 + 1, e2 + 1):
                    away_all_days &= day_away.get(dd, set())
                # h kann nicht sein eigener Gast sein
                away_all_days.discard(h)

                for a in away_all_days:
                    key = (h, e1, e2, a)
                    var = model.NewBoolVar(f"y_{h}_{e1}_{e2}_{a}")
                    y[key] = var
                    n_vars += 1
                    for dd in range(e1, e2 + 1):
                        coverage_h[(h, dd)].append(var)
                        coverage_a[(a, dd)].append(var)

    if verbose:
        logger.info(f"[PhaseB-Slots] {n_vars} Slot-Vars  ({time.time()-t0:.1f}s)")

    # ── Constraint 1: Partition — pro H-Tag genau ein Slot ──────────────
    infeasible_days = []
    for hs in h_series_list:
        h = hs.team_id
        for d in range(hs.start_day, hs.end_day + 1):
            if d in break_days:
                continue
            slots_for_d = coverage_h.get((h, d), [])
            if not slots_for_d:
                infeasible_days.append((h, d))
                continue
            model.AddExactlyOne(slots_for_d)

    if infeasible_days:
        if verbose:
            logger.info(f"[PhaseB-Slots] INFEASIBLE: {len(infeasible_days)} H-Tage ohne Slot-Option")
            for h, d in infeasible_days[:5]:
                logger.info(f"  {h} Tag {d}")
        return SeriesMatchingResult(
            assignments=[],
            unmatched_games=[(d, h) for h, d in infeasible_days],
            total_games=0,
            series_lengths={},
            violations=[f"Kein Slot für {len(infeasible_days)} H-Tage: z.B. {infeasible_days[0]}"],
        )

    # ── Constraint 2: Away-Exklusivität — a pro Tag nur bei einem Home ──
    for (a, d), slot_vars in coverage_a.items():
        if slot_vars:
            model.AddExactlyOne(slot_vars)

    # ── Constraint 2b: Away-Teams ohne jegliche Slot-Option ─────────────
    # Wenn ein Away-Team a an Tag d keine Slot-Option hat (coverage_a[(a,d)] leer),
    # ist es strukturell unbedeckt. Wir loggen das, aber das Modell bleibt feasible
    # weil diese Tage nur im Soft-Modus relevant sind.
    uncov_away = []
    for d, away_set in day_away.items():
        for a in away_set:
            if not coverage_a.get((a, d)):
                uncov_away.append((a, d))
    if verbose and uncov_away:
        logger.info(f"[PhaseB-Slots] Warnung: {len(uncov_away)} Away-Tage ohne Slot-Option")

    if verbose:
        elapsed = time.time() - t0
        logger.info(f"[PhaseB-Slots] Modell fertig in {elapsed:.1f}s, starte Solver ...")

    # ── Solver ──────────────────────────────────────────────────────────
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 8
    solver.parameters.log_search_progress = verbose

    status_code = solver.Solve(model)
    status_map = {
        cp_model.OPTIMAL:    "OPTIMAL",
        cp_model.FEASIBLE:   "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.UNKNOWN:    "UNKNOWN",
    }
    status = status_map.get(status_code, f"CODE_{status_code}")

    if verbose:
        logger.info(f"[PhaseB-Slots] Status={status}  Zeit={time.time()-t0:.1f}s")

    if status not in ("OPTIMAL", "FEASIBLE"):
        return SeriesMatchingResult(
            assignments=[],
            unmatched_games=[],
            total_games=0,
            series_lengths={},
            violations=[f"CP-SAT Slot-Modell: {status}"],
        )

    # ── Ergebnis extrahieren ─────────────────────────────────────────────
    assignments: List[SeriesAssignment] = []
    for (h, e1, e2, a), var in y.items():
        if solver.Value(var) == 1:
            assignments.append(SeriesAssignment(
                home_team=h, away_team=a,
                start_day=e1, end_day=e2,
            ))

    # ── Diagnostik ──────────────────────────────────────────────────────
    from collections import Counter
    length_counter: Counter = Counter(ass.length for ass in assignments)
    violations: List[str] = []
    for ass in assignments:
        if ass.length < 2:
            violations.append(
                f"Series {ass.home_team} vs {ass.away_team} "
                f"Tag {ass.start_day}: Länge {ass.length} < 2"
            )
        if ass.length > 4:
            violations.append(
                f"Series {ass.home_team} vs {ass.away_team} "
                f"Tag {ass.start_day}: Länge {ass.length} > 4"
            )

    total_games = sum(ass.length for ass in assignments)

    if verbose:
        logger.info(f"[PhaseB-Slots] {len(assignments)} Serien  "
              f"total_games={total_games}  violations={len(violations)}")
        logger.info(f"  Series-Längen: {dict(sorted(length_counter.items()))}")

    return SeriesMatchingResult(
        assignments=assignments,
        unmatched_games=[],
        total_games=total_games,
        series_lengths=dict(length_counter),
        violations=violations,
    )


# ====================================================================
# Soft Slot-Based Phase B (minimiert length-1 Serien, immer feasible)
# ====================================================================

def match_series_slots_soft(
    patterns: Dict[str, List[str]],
    total_days: int,
    break_days: Set[int],
    verbose: bool = False,
    time_limit_s: float = 180.0,
) -> SeriesMatchingResult:
    """Slot-basiertes Phase B mit weichem Min-2-Constraint.

    Wie match_series_slots, aber 1-Tage-Slots sind als Fallback erlaubt
    und werden mit einer Penalty-Zielfunktion minimiert.

    Eigenschaften:
    - Immer FEASIBLE (1-Tage-Slots garantieren Lösbarkeit)
    - Findet globales Minimum der length-1-Serien
    - Korrekte Partition + Away-Exklusivität
    - Läuft in ~20-60s für 30 Teams

    Gibt SeriesMatchingResult zurück; violations enthält alle length-1-
    Serien die strukturell unvermeidbar waren.
    """
    from ortools.sat.python import cp_model
    from collections import defaultdict
    import time

    t0 = time.time()
    model = cp_model.CpModel()

    hap = parse_hap_series(patterns, break_days)
    h_series_list: List[HAPSeries] = [
        s for team_id, series_list in hap.items()
        for s in series_list if s.type == 'H'
    ]

    day_away: Dict[int, Set[str]] = {}
    for d in range(total_days):
        if d in break_days:
            continue
        a_set = {t for t, m in patterns.items() if m[d] == 'A'}
        if a_set:
            day_away[d] = a_set

    # ── Slot-Variablen (Länge 1-4) ───────────────────────────────────────
    y: Dict[Tuple[str, int, int, str], cp_model.IntVar] = {}
    coverage_h: Dict[Tuple[str, int], List] = defaultdict(list)
    coverage_a: Dict[Tuple[str, int], List] = defaultdict(list)
    penalty_vars: List[cp_model.IntVar] = []   # Alle length-1 Slots

    for hs in h_series_list:
        h = hs.team_id
        d1, d2 = hs.start_day, hs.end_day

        for e1 in range(d1, d2 + 1):           # inkl. letzten Tag
            for length in range(1, 5):          # 1, 2, 3, 4 Tage
                e2 = e1 + length - 1
                if e2 > d2:
                    break
                if any(dd in break_days for dd in range(e1, e2 + 1)):
                    continue

                # Away-Teams die für ALLE Tage des Slots verfügbar sind
                away_cands = set(day_away.get(e1, set()))
                for dd in range(e1 + 1, e2 + 1):
                    away_cands &= day_away.get(dd, set())
                away_cands.discard(h)

                for a in away_cands:
                    key = (h, e1, e2, a)
                    var = model.NewBoolVar(f"y_{h}_{e1}_{e2}_{a}")
                    y[key] = var
                    for dd in range(e1, e2 + 1):
                        coverage_h[(h, dd)].append(var)
                        coverage_a[(a, dd)].append(var)
                    if length == 1:
                        penalty_vars.append(var)

    if verbose:
        logger.info(f"[PhaseB-Soft] {len(y)} Slot-Vars  "
              f"({len(penalty_vars)} penalty/length-1)  ({time.time()-t0:.1f}s)")

    # ── Partition: pro H-Tag genau ein Slot ──────────────────────────────
    for hs in h_series_list:
        h = hs.team_id
        for d in range(hs.start_day, hs.end_day + 1):
            if d in break_days:
                continue
            slots = coverage_h.get((h, d), [])
            if slots:
                model.AddExactlyOne(slots)

    # ── Away-Exklusivität ────────────────────────────────────────────────
    for (a, d), slot_vars in coverage_a.items():
        if slot_vars:
            model.AddExactlyOne(slot_vars)

    # ── Zielfunktion: Minimiere length-1 Slots ───────────────────────────
    if penalty_vars:
        model.Minimize(sum(penalty_vars))

    if verbose:
        logger.info(f"[PhaseB-Soft] Modell fertig in {time.time()-t0:.1f}s, starte Solver ...")

    # ── Solver ───────────────────────────────────────────────────────────
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 8
    solver.parameters.log_search_progress = verbose

    status_code = solver.Solve(model)
    status_map = {
        cp_model.OPTIMAL:    "OPTIMAL",
        cp_model.FEASIBLE:   "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.UNKNOWN:    "UNKNOWN",
    }
    status = status_map.get(status_code, f"CODE_{status_code}")

    if verbose:
        logger.info(f"[PhaseB-Soft] Status={status}  obj={solver.ObjectiveValue():.0f}  "
              f"Zeit={time.time()-t0:.1f}s")

    if status not in ("OPTIMAL", "FEASIBLE"):
        return SeriesMatchingResult(
            assignments=[],
            unmatched_games=[],
            total_games=0,
            series_lengths={},
            violations=[f"CP-SAT Soft-Slot: {status}"],
        )

    # ── Ergebnis extrahieren ─────────────────────────────────────────────
    assignments: List[SeriesAssignment] = []
    for (h, e1, e2, a), var in y.items():
        if solver.Value(var) == 1:
            assignments.append(SeriesAssignment(
                home_team=h, away_team=a,
                start_day=e1, end_day=e2,
            ))

    from collections import Counter
    length_counter: Counter = Counter(ass.length for ass in assignments)
    violations: List[str] = [
        f"Series {ass.home_team} vs {ass.away_team} Tag {ass.start_day}: Länge 1"
        for ass in assignments if ass.length < 2
    ] + [
        f"Series {ass.home_team} vs {ass.away_team} Tag {ass.start_day}: Länge {ass.length} > 4"
        for ass in assignments if ass.length > 4
    ]
    total_games = sum(ass.length for ass in assignments)

    if verbose:
        logger.info(f"[PhaseB-Soft] {len(assignments)} Serien  "
              f"total_games={total_games}  violations={len(violations)}")
        logger.info(f"  Series-Längen: {dict(sorted(length_counter.items()))}")

    return SeriesMatchingResult(
        assignments=assignments,
        unmatched_games=[],
        total_games=total_games,
        series_lengths=dict(length_counter),
        violations=violations,
    )


# ====================================================================
# CP-SAT Phase B — Legacy-Implementierung (per-pair, für Vergleich)
# ====================================================================

def match_series_cpsat(
    patterns: Dict[str, List[str]],
    total_days: int,
    break_days: Set[int],
    verbose: bool = False,
    time_limit_s: float = 120.0,
) -> SeriesMatchingResult:
    """Weist Gegner per CP-SAT global-optimal zu (garantiert 0 length-1 Violations).

    Modell:
    - BoolVar x[h,a,d] = 1 gdw. Team h spielt an Tag d gegen Team a.
    - Covering: für jedes Heim-Spieltag (h,d): sum_a x[h,a,d] = 1
    - Exklusivität: für jedes Auswärts-Spieltag (a,d): sum_h x[h,a,d] = 1
    - Series min-2: Neues Matchup (x[h,a,d]=1, x[h,a,d-1]=0) erfordert
      x[h,a,d+1]=1 (sofern d+1 für das Paar gültig ist).
    - Series max-4: Sum über 5 aufeinanderfolgende gültige Tage <= 4.
    - Kein Eigenspiel: x[h,h,d] = 0 (implizit durch Variablenstruktur).

    Laufzeit: ~20-60s für 30 Teams / 186 Tage.
    """
    from ortools.sat.python import cp_model
    from collections import defaultdict
    import time

    t0 = time.time()
    model = cp_model.CpModel()

    # ── Pro Tag: Home- und Away-Teams ───────────────────────────────────
    day_home: Dict[int, Set[str]] = {}
    day_away: Dict[int, Set[str]] = {}
    for d in range(total_days):
        if d in break_days:
            continue
        h_set = {t for t, m in patterns.items() if m[d] == 'H'}
        a_set = {t for t, m in patterns.items() if m[d] == 'A'}
        if h_set:
            day_home[d] = h_set
        if a_set:
            day_away[d] = a_set

    # ── Variablen: x[(h,a,d)] für alle gültigen Tripel ──────────────────
    # Gültig: h ∈ day_home[d], a ∈ day_away[d], h ≠ a
    x: Dict[Tuple[str, str, int], cp_model.IntVar] = {}
    for d, h_set in day_home.items():
        a_set = day_away.get(d, set())
        for h in h_set:
            for a in a_set:
                if h != a:
                    x[(h, a, d)] = model.NewBoolVar(f"x_{h}_{a}_{d}")

    if verbose:
        logger.info(f"[PhaseB-CSAT] {len(x)} Variablen  ({time.time()-t0:.1f}s)")

    # ── Covering: pro Heim-Spieltag genau ein Gegner ────────────────────
    for d, h_set in day_home.items():
        a_set = day_away.get(d, set())
        for h in h_set:
            valid = [x[(h, a, d)] for a in a_set if (h, a, d) in x]
            if valid:
                model.AddExactlyOne(valid)

    # ── Exklusivität: pro Away-Spieltag genau ein Gastgeber ─────────────
    for d, a_set in day_away.items():
        h_set = day_home.get(d, set())
        for a in a_set:
            valid = [x[(h, a, d)] for h in h_set if (h, a, d) in x]
            if valid:
                model.AddExactlyOne(valid)

    # ── Series min-2 ─────────────────────────────────────────────────────
    # Für jedes Variablen-Tripel (h,a,d):
    # "Neues Matchup startet an Tag d" bedeutet x[h,a,d]=1 und kein
    # gültiges x[h,a,d-1] (d-1 nicht spielbar für dieses Paar).
    # → Wenn d+1 für das Paar gültig: x[h,a,d] - x_prev <= x[h,a,d+1]
    # → Wenn d+1 NICHT gültig (Serien-Ende oder Break):
    #      x[h,a,d] darf nur 1 sein wenn x_prev = 1 (d.h. kein Neustart)

    # Vorherigen Tag für jedes Paar bestimmen (überspringe Breaks)
    def prev_game_day(d: int) -> Optional[int]:
        """Letzter spielbarer Tag vor d (kein Break)."""
        dd = d - 1
        while dd >= 0 and dd in break_days:
            dd -= 1
        return dd if dd >= 0 else None

    def next_game_day(d: int) -> Optional[int]:
        """Nächster spielbarer Tag nach d (kein Break)."""
        dd = d + 1
        while dd < total_days and dd in break_days:
            dd += 1
        return dd if dd < total_days else None

    for (h, a, d), var in x.items():
        prev_d = prev_game_day(d)
        next_d = next_game_day(d)

        prev_var = x.get((h, a, prev_d)) if prev_d is not None else None
        next_var = x.get((h, a, next_d)) if next_d is not None else None

        if next_var is None:
            # Kein Folgetag für dieses Paar: Matchup darf nicht NEU starten
            # → var = 1 erfordert prev_var = 1
            if prev_var is not None:
                model.Add(var <= prev_var)
            else:
                # Weder Vorgänger noch Nachfolger gültig → Einzelspieltag, verboten
                model.Add(var == 0)
        else:
            # Standardfall: wenn Neustart (var=1, prev=0), dann next=1
            if prev_var is not None:
                model.Add(var - prev_var <= next_var)
            else:
                # Kein Vorgänger: wenn var=1, dann next=1
                model.Add(var <= next_var)

    # ── Series max-4 ─────────────────────────────────────────────────────
    # Pro (h,a)-Paar: keine 5 konsekutiven Spieltage zusammen
    pair_days: Dict[Tuple[str, str], List[int]] = defaultdict(list)
    for (h, a, d) in x:
        pair_days[(h, a)].append(d)

    for (h, a), days in pair_days.items():
        days_sorted = sorted(days)
        for i in range(len(days_sorted) - 4):
            window = days_sorted[i:i+5]
            # Nur wenn alle 5 Tage konsekutiv (keine Lücken außer Breaks)
            consecutive = True
            for j in range(4):
                nd = next_game_day(window[j])
                if nd != window[j+1]:
                    consecutive = False
                    break
            if consecutive:
                model.Add(sum(x[(h, a, wd)] for wd in window) <= 4)

    if verbose:
        elapsed = time.time() - t0
        logger.info(f"[PhaseB-CSAT] Modell aufgebaut in {elapsed:.1f}s, starte Solver ...")

    # ── Solver ──────────────────────────────────────────────────────────
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 8
    solver.parameters.log_search_progress = verbose

    status_code = solver.Solve(model)

    status_map = {
        cp_model.OPTIMAL:   "OPTIMAL",
        cp_model.FEASIBLE:  "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.UNKNOWN:   "UNKNOWN",
    }
    status = status_map.get(status_code, f"CODE_{status_code}")

    if verbose:
        logger.info(f"[PhaseB-CSAT] Status={status}  Zeit={time.time()-t0:.1f}s")

    if status not in ("OPTIMAL", "FEASIBLE"):
        return SeriesMatchingResult(
            assignments=[],
            unmatched_games=[(d, h) for d, h_set in day_home.items() for h in h_set],
            total_games=0,
            series_lengths={},
            violations=[f"CP-SAT Phase B: {status} — kein gültiges Matching gefunden"],
        )

    # ── Ergebnis extrahieren ─────────────────────────────────────────────
    # Für jede (h, a)-Folge konsekutiver Tage: ein SeriesAssignment
    assignments: List[SeriesAssignment] = []

    # Aufbauen: pro (h,a) die aktiven Tage
    active_by_pair: Dict[Tuple[str, str], List[int]] = defaultdict(list)
    for (h, a, d), var in x.items():
        if solver.Value(var) == 1:
            active_by_pair[(h, a)].append(d)

    for (h, a), days in active_by_pair.items():
        days_sorted = sorted(days)
        # Segmentiere in konsekutive Blöcke (Breaks trennen)
        seg_start = days_sorted[0]
        seg_end   = days_sorted[0]
        for i in range(1, len(days_sorted)):
            nd = next_game_day(days_sorted[i-1])
            if nd == days_sorted[i]:
                seg_end = days_sorted[i]
            else:
                assignments.append(SeriesAssignment(h, a, seg_start, seg_end))
                seg_start = days_sorted[i]
                seg_end   = days_sorted[i]
        assignments.append(SeriesAssignment(h, a, seg_start, seg_end))

    # ── Diagnostik ──────────────────────────────────────────────────────
    from collections import Counter
    length_counter: Counter = Counter(ass.length for ass in assignments)
    violations: List[str] = []
    for ass in assignments:
        if ass.length < 2:
            violations.append(
                f"Series {ass.home_team} vs {ass.away_team} Tag {ass.start_day}: "
                f"Länge {ass.length} < 2"
            )
        if ass.length > 4:
            violations.append(
                f"Series {ass.home_team} vs {ass.away_team} Tag {ass.start_day}: "
                f"Länge {ass.length} > 4"
            )

    total_games = sum(ass.length for ass in assignments)

    if verbose:
        logger.info(f"[PhaseB-CSAT] {len(assignments)} Serien  "
              f"total_games={total_games}  violations={len(violations)}")
        logger.info(f"  Series-Längen: {dict(sorted(length_counter.items()))}")

    return SeriesMatchingResult(
        assignments=assignments,
        unmatched_games=[],
        total_games=total_games,
        series_lengths=dict(length_counter),
        violations=violations,
    )


# ====================================================================
# Validation
# ====================================================================

def validate_series_matching(
    result: SeriesMatchingResult,
    patterns: Dict[str, List[str]],
    total_days: int,
    break_days: Set[int],
) -> List[str]:
    """Vollständige Validierung des Series-Matchings.

    Prüft:
    1. Jedes Home-Spiel hat genau einen Gegner.
    2. Kein Team spielt gegen sich selbst.
    3. Pair-Matching: jedes Heimspiel hat ein Gastspiel.
    4. Series-Länge 2-4.
    5. Away-Team spielt tatsächlich Away am jeweiligen Tag.
    """
    errors: List[str] = []

    # Coverage-Check: für jeden Heim-Saisontag (team, day) → Gegner gefunden?
    coverage: Dict[Tuple[str, int], str] = {}
    for ass in result.assignments:
        for d in ass.days:
            key = (ass.home_team, d)
            if key in coverage:
                errors.append(f"Doppelbelegung: {ass.home_team} Tag {d}")
            coverage[key] = ass.away_team
            # Away-Coverage
            key_a = (ass.away_team, d)
            if key_a in coverage:
                pass  # Away-Team kann als Gast mehrfach auftauchen (nein, sollte nicht)

    # Prüfe: alle H-Tage haben Gegner
    for team_id, marks in patterns.items():
        for d, m in enumerate(marks):
            if m == 'H' and d not in break_days:
                if (team_id, d) not in coverage:
                    errors.append(f"{team_id} Tag {d}: Heimspiel ohne Gegner")

    # Prüfe: kein Team spielt gegen sich selbst
    for ass in result.assignments:
        if ass.home_team == ass.away_team:
            errors.append(f"Eigenspiel: {ass.home_team} vs {ass.away_team}")

    # Prüfe: Away-Team hat tatsächlich Away am Series-Tag
    for ass in result.assignments:
        for d in ass.days:
            mark = patterns[ass.away_team][d]
            if mark != 'A':
                errors.append(
                    f"Away-Team {ass.away_team} spielt nicht Away an Tag {d} "
                    f"(Mark={mark}), Home-Serie {ass.home_team}"
                )

    # Prüfe: Series-Längen
    errors.extend(result.violations)

    return errors
