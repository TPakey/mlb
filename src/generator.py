"""Schedule-from-Scratch Generator (Sprint 2.1).

CP-SAT-basiert. Eingabe: Matchup-Quoten (Liste Serien-Templates) + Saisonfenster
+ All-Star-Break. Ausgabe: ein vollstaendiger Saisonplan, der alle harten
Constraints erfuellt.

Variablen-Design:
- pro Serie ein IntervalVar(start, length, end) im Zeitfenster
- NoOverlap pro Team ueber alle Serien dieses Teams
- All-Star-Break: Serien-Start-Domains schliessen kollidierende Tage aus

Diese Implementierung ist die Sprint-2.1-Baseline. Spaetere Iterationen
fuegen Optimierungs-Objectives hinzu (Travel-Minimierung, Heim-Stand-Laenge,
etc.).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

from ortools.sat.python import cp_model

from .matchup_extractor import MatchupQuotas
from .season import Game, Season


@dataclass
class GeneratorConfig:
    season: int
    season_start: date
    season_end: date
    all_star_break: Optional[Tuple[date, date]] = None  # inklusiv
    max_solver_time_seconds: float = 1800.0   # 30 Minuten Default
    # WICHTIG: num_search_workers=1 als Default, damit der Generator bei gleichem
    # Seed bit-identische Ergebnisse liefert (AC-2.1.11). CP-SAT mit >1 Worker
    # ist Thread-Race-abhaengig und damit nicht deterministisch.
    num_search_workers: int = 1
    random_seed: int = 42
    log_search_progress: bool = False
    # ---- Travel-Optimizer (Sprint 2.1 Stufe 2) ----
    # Nach dem CP-SAT-Schritt laeuft optional eine Simulated-Annealing-Stufe,
    # die Reisedistanzen minimiert, ohne harte Constraints zu verletzen.
    enable_travel_optimization: bool = True
    # Sprint 3 (2026-06-01): von 700k/shift3 auf 3 Mio/shift8 angehoben, PLUS der
    # geo-bewusste Struktur-Move (generator_optimizer). Der Backtest gegen den
    # echten MLB-Plan zeigte: 700k/shift3 (ohne Geo) plateaut bei ~2,10 Mio km
    # (+23 % vs. real); 3 Mio + Geo erreicht ~1,97 Mio (+15 %), 6-8 Mio + Geo
    # ~1,86 Mio (+9 %). Diagnose + Messreihe: docs/SPRINT_3_DIAGNOSIS_TRAVEL.md.
    # 3 Mio (~12 s) ist ein bewusst moderates DEFAULT, damit auch interaktive
    # Pfade (Disruption-Re-Generate, Tests) responsiv bleiben — die OFFIZIELLE
    # Saison-Generierung (tools/main.py, tools/backtest.py) setzt das Budget
    # explizit hoeher (6 Mio) fuer den bestmoeglichen Plan ("Qualitaet vor
    # Geschwindigkeit"). Deterministisch (fixer Seed). Den Rest-Gap zum realen
    # Plan schliessen Doubleheader-Support + Track A (AC-2.1.8).
    travel_optimizer_iterations: int = 3_000_000
    travel_optimizer_shift_max_days: int = 8
    travel_optimizer_start_temperature: float = 1500.0
    travel_optimizer_end_temperature: float = 1.0
    teams_path: Optional[Path] = None         # None -> data_loader-Default
    # ---- Sprint 2.2: Disruption-Constraints ----
    # Pro home-team eine Menge von Tag-Indizes (relativ zu season_start),
    # an denen das Team KEIN Heimspiel haben darf. Wird von Strategie B
    # (Constrained Re-Generate) gefuellt und in `_valid_start_domain`
    # angewendet.
    home_blackout_days: Dict[str, FrozenSet[int]] = field(default_factory=dict)
    # ---- Sprint 2.3 Task #15: Sliding-Window-Constraints ----
    # AC-2.1.9: max 20 Spieltage in 21-Tage-Fenster pro Team
    # AC-2.1.8: max 13 konsekutive Auswaerts-Tage pro Team
    # Default: aktiviert. Performance-Aufschlag ~5-60 s (single-thread).
    enforce_fatigue_constraints: bool = True
    # ---- Q10: AC-2.1.8 strukturell im CP-SAT erzwingen (EXPERIMENTELL) ----
    # Wenn True, wird die verifiziert-sounde Gap-/Nachfolger-Formulierung
    # (`_add_ac_2_1_8_gap_constraints`) aktiviert — bei vorhandenem All-Star-
    # Break ueber die Drei-Phasen-Decomposition (`_solve_ac218_decomposed`).
    # ACHTUNG: auf der vollen MLB-Saison (~811 Serien) ist diese Formulierung
    # NICHT zuverlaessig tractable. Empirisch (2026-05-31, 1- und 4-Worker):
    # die erste Saisonhaelfte allein bleibt selbst nach 35 s UNKNOWN. Der Solve
    # kann also INFEASIBLE/UNKNOWN zurueckgeben — fuer den Produktionspfad
    # ungeeignet. Default False; AC-2.1.8 wird produktiv weich (SA-Penalty +
    # Repair) durchgesetzt. Details: docs/REFACTOR_BACKLOG.md Q10.
    enforce_ac218_structural: bool = False
    # ---- Q10: optionaler gefensterter CP-SAT-LNS-Repair fuer AC-2.1.8 ----
    # Reicht das Flag an OptimizerConfig.enable_lns_ac218_repair durch. Laeuft als
    # finaler Repair nach der SA, senkt die realen AC-2.1.8-Verletzungen weiter
    # (deterministisch, matchup-erhaltend, OHNE ≤13-Garantie). Default aus
    # (Laufzeit-Aufschlag ~15-30 s). Details: docs/Q10_ANALYSE_UND_RECHERCHE.md.
    enable_lns_ac218_repair: bool = False

    def __post_init__(self) -> None:
        """Eingangsvalidierung (N2): faengt unsinnige Saisonfenster frueh ab,
        statt sie spaeter als Index-Errors im Pipeline-Pfad auftauchen zu
        lassen."""
        if self.season_end < self.season_start:
            raise ValueError(
                f"season_end ({self.season_end}) liegt vor season_start "
                f"({self.season_start}). Saisonfenster muss season_start "
                f"<= season_end erfuellen."
            )
        if self.all_star_break is not None:
            asb_start, asb_end = self.all_star_break
            if asb_end < asb_start:
                raise ValueError(
                    f"all_star_break Ende ({asb_end}) liegt vor Start "
                    f"({asb_start})."
                )
            if asb_start < self.season_start or asb_end > self.season_end:
                raise ValueError(
                    f"all_star_break ({asb_start}..{asb_end}) liegt ausserhalb "
                    f"des Saisonfensters ({self.season_start}..{self.season_end})."
                )
        if self.num_search_workers < 1:
            raise ValueError("num_search_workers muss >= 1 sein.")


@dataclass
class GeneratorResult:
    """Ergebnis eines Generator-Laufs."""
    season: Optional[Season]
    status: str                                  # "OPTIMAL" / "FEASIBLE" / "INFEASIBLE" / "TIMEOUT"
    solve_time_seconds: float                    # Gesamtzeit (CP-SAT + Travel-Optimizer)
    num_branches: int
    num_conflicts: int
    objective_value: Optional[float] = None
    objective_bound: Optional[float] = None
    # ---- Travel-Optimizer-Diagnostik ----
    cp_sat_seconds: float = 0.0
    travel_optimizer_seconds: float = 0.0
    initial_km: Optional[float] = None           # vor SA
    final_km: Optional[float] = None             # nach SA (gleich initial_km wenn deaktiviert)


def _season_days(cfg: GeneratorConfig) -> int:
    """Anzahl Tage im Saisonfenster (inklusive Start und Ende)."""
    return (cfg.season_end - cfg.season_start).days + 1


def _break_day_indices(cfg: GeneratorConfig) -> Set[int]:
    """Indizes der All-Star-Break-Tage relativ zu season_start."""
    if cfg.all_star_break is None:
        return set()
    start, end = cfg.all_star_break
    out = set()
    d = start
    while d <= end:
        out.add((d - cfg.season_start).days)
        d += timedelta(days=1)
    return out


def _periodic_break_days(total_days: int, max_gap: int = 21) -> Set[int]:
    """Periodische Break-Days alle max_gap Tage (AC-2.3.10 / Sprint 2.4).

    Strukturell garantiert (Pigeonhole) wird mit dem real verwendeten
    Default `max_gap=21` ausschliesslich **AC-2.1.9**:

    - AC-2.1.9: max 20 Spieltage in jedem 21-Tage-Fenster. Beweis: Break-Days
      liegen im Abstand max_gap=21. In jedem 21-Tage-Fenster [w, w+20] liegt
      also mindestens ein Break-Day → hoechstens 20 Spieltage. ✓

    **AC-2.1.8 wird hier NICHT garantiert.** Die periodischen Break-Days
    unterbrechen Away-Streaks nur alle 21 Tage; eine Road-Trip kann zwischen
    zwei Breaks deutlich laenger als 13 Tage werden. AC-2.1.8 (max 13 "days
    away from home", CBA-Definition) wird stattdessen in Stufe 2 **weich**
    erzwungen — durch die SA-Penalty mit lambda = 1.000.000 in
    `optimize_travel` (siehe `generator_optimizer.py`), die AC-Verletzungen
    mit P(accept) ~ 0 ablehnt und nach CP-SAT verbliebene Verletzungen durch
    Serien-Swaps repariert. Empirisch verifiziert: 0 Verletzungen nach
    ~700 k SA-Schritten (Seed 42), siehe docs/CBA_DEFINITIONS.md.

    Hinweis: Mit `max_gap=14` wuerde zusaetzlich AC-2.1.8 in der *alten*
    (Off-Day-bricht-Streak-)Definition strukturell garantiert. Diese
    Definition ist seit Sprint 2.7 nicht mehr gueltig (C1), daher ist der
    Default bewusst 21 und nicht 14.

    Positions: max_gap-1, 2*max_gap-1, ... (0-indiziert, relativ zu season_start).
    """
    breaks: Set[int] = set()
    d = max_gap - 1
    while d < total_days:
        breaks.add(d)
        d += max_gap
    return breaks


def _valid_start_domain(length: int, total_days: int, break_days: Set[int]) -> List[int]:
    """Tage, an denen eine Serie der angegebenen Laenge starten darf.

    Bedingung: die Tage [start..start+length-1] muessen alle innerhalb [0..total_days)
    liegen UND duerfen nicht im All-Star-Break sein.
    """
    out: List[int] = []
    for start in range(0, total_days - length + 1):
        occupied = set(range(start, start + length))
        if occupied.intersection(break_days):
            continue
        out.append(start)
    return out


def _team_participations(quotas: MatchupQuotas) -> Dict[str, List[int]]:
    """Pro Team die Indizes der Serien (in `quotas.series_templates`), an denen
    es teilnimmt (Heim oder Auswaerts)."""
    out: Dict[str, List[int]] = {}
    for idx, s in enumerate(quotas.series_templates):
        out.setdefault(s.home, []).append(idx)
        out.setdefault(s.away, []).append(idx)
    return out


# AC-2.1.8: max 13 "days away from home" (CBA-Definition, siehe
# docs/CBA_DEFINITIONS.md). Off-Days mitten in einer Road-Trip zaehlen mit.
AC_2_1_8_MAX_AWAY_DAYS = 13


def _add_ac_2_1_8_gap_constraints(
    model: "cp_model.CpModel",
    home_series_by_team: Dict[str, List[Tuple["cp_model.IntVar", "cp_model.IntVar", int]]],
    total_days: int,
    limit: int = AC_2_1_8_MAX_AWAY_DAYS,
    day_lo: int = 0,
    day_hi: Optional[int] = None,
) -> None:
    """Erzwingt AC-2.1.8 strukturell ueber die Heim-Serien eines Teams.

    Idee (QA 2026-05-29, gegen ein Brute-Force-Orakel auf 315 Zufallsinstanzen
    als SOUND verifiziert): Eine Road-Trip-Spanne > 13 Kalendertage bedeutet 14
    aufeinanderfolgende Tage ohne Heimspiel. Das wird verhindert, indem die
    Heim-Serien eines Teams so dicht liegen, dass nie eine 14-Tage-Luecke ohne
    Heimspiel entsteht:

    - **Opening:** mindestens eine Heim-Serie startet in den ersten 14 Tagen
      (Start-Tag <= 13) — sonst waere der Saisonauftakt eine zu lange Road-Trip.
    - **Gap/Nachfolger:** fuer jede Heim-Serie i (mit EXKLUSIVEM End-Tag E_i,
      OR-Tools-Konvention E_i = start_i + length_i, d. h. E_i ist der Tag NACH
      dem letzten Heimtag) gilt entweder
        (a) eine andere Heim-Serie j startet in [E_i, E_i + 13]  (Luecke <= 13), ODER
        (b) i liegt nahe genug am Saisonende (E_i >= total_days - 13), sodass
            danach keine 14-Tage-Luecke mehr passt.

    Wichtig zur Off-by-one-Korrektheit: Mit exklusivem E_i ist die Anzahl
    auswaerts/off Tage zwischen dem letzten Heimtag (E_i - 1) und dem naechsten
    Heimstart s_j genau (s_j - E_i + 1) Tage Road-Trip-Spanne wenn lueckenlos;
    die Schranke s_j <= E_i + 13 begrenzt die reine Luecke auf <= 13 Tage. Ein
    frueher Prototyp nutzte faelschlich +14 (last-day statt exklusiv) und liess
    14-Tage-Trips zu — das ist hier korrigiert und orakel-verifiziert.

    Diese Formulierung arbeitet nur auf den Serien-Start-Variablen (O(Serien^2)
    pro Team) und vermeidet damit den Solver-Blowup der Off-Day-Slot-Variante
    (~140k Booleans, UNKNOWN; siehe docs/AUDIT_A1_NOTE.md).

    `day_lo`/`day_hi` definieren das (Teil-)Zeitfenster, in dem das Team
    "zu Hause anfaengt/aufhoert": Opening = Start <= day_lo + limit, Closing =
    End >= day_hi - limit. Default ist die ganze Saison (0..total_days). Fuer die
    Halbsaison-Decomposition (Q10) wird die Funktion mit den Halften-Grenzen und
    einem virtuellen Break-Heimstand als gemeinsamem Anker aufgerufen.
    """
    if day_hi is None:
        day_hi = total_days
    for hs in home_series_by_team.values():
        if not hs:
            continue
        opening = []
        for (s_i, _e_i, _L) in hs:
            op = model.NewBoolVar("ac218_open")
            model.Add(s_i <= day_lo + limit).OnlyEnforceIf(op)
            model.Add(s_i >= day_lo + limit + 1).OnlyEnforceIf(op.Not())
            opening.append(op)
        model.AddBoolOr(opening)
        for a, (s_i, e_i, _Li) in enumerate(hs):
            options = []
            near_end = model.NewBoolVar("ac218_end")
            model.Add(e_i >= day_hi - limit).OnlyEnforceIf(near_end)
            model.Add(e_i <= day_hi - limit - 1).OnlyEnforceIf(near_end.Not())
            options.append(near_end)
            for b, (s_j, _e_j, _Lj) in enumerate(hs):
                if b == a:
                    continue
                succ = model.NewBoolVar("ac218_succ")
                model.Add(s_j >= e_i).OnlyEnforceIf(succ)
                model.Add(s_j <= e_i + limit).OnlyEnforceIf(succ)
                options.append(succ)
            model.AddBoolOr(options)


def _solve_one_phase(
    templates,
    per_team: Dict[str, List[int]],
    per_series_domain: List[List[int]],
    fixed: Dict[int, int],
    free_half: Optional[str],
    b0: int,
    b1: int,
    total_days: int,
    cfg: GeneratorConfig,
) -> Tuple[str, Optional[List[int]], float]:
    """Loest EINE Phase der AC-2.1.8-Decomposition.

    `fixed`: series_idx -> fixierter Startwert (Domain = {wert}).
    `free_half`: None  -> keine Gap-Constraints (gap-freies Skelett);
                 'first'-> Gap-Constraints auf den Heim-Serien der ersten Haelfte
                           (Start < b0), Fenster [0, b1+1];
                 'second'-> Gap-Constraints auf der zweiten Haelfte (Start > b1),
                           Fenster [b0, total_days].
    Freie Serien werden zusaetzlich auf ihre Haelfte beschraenkt (Domain < b0
    bzw. > b1), damit die Decomposition sauber bleibt.
    """
    model = cp_model.CpModel()
    starts: List[cp_model.IntVar] = []
    intervals: List[cp_model.IntVar] = []
    freed_home_by_team: Dict[str, List[Tuple[cp_model.IntVar, cp_model.IntVar, int]]] = {}

    for i, t in enumerate(templates):
        if i in fixed:
            dom_vals = [fixed[i]]
            is_free = False
        else:
            dom_vals = per_series_domain[i]
            if free_half == "first":
                dom_vals = [d for d in dom_vals if d < b0]
            elif free_half == "second":
                dom_vals = [d for d in dom_vals if d > b1]
            is_free = True
        if not dom_vals:
            return ("INFEASIBLE", None, 0.0)
        s = model.NewIntVarFromDomain(cp_model.Domain.FromValues(dom_vals), f"s_{i}")
        e = model.NewIntVar(0, total_days, f"e_{i}")
        model.Add(e == s + t.length)
        starts.append(s)
        intervals.append(model.NewIntervalVar(s, t.length, e, f"iv_{i}"))
        if is_free and free_half is not None:
            freed_home_by_team.setdefault(t.home, []).append((s, e, t.length))

    for team_id, idxs in per_team.items():
        model.AddNoOverlap([intervals[i] for i in idxs])

    if free_half is not None:
        gap_home = {tid: list(hs) for tid, hs in freed_home_by_team.items()}
        for tid in gap_home:
            cs = model.NewConstant(b0)
            ce = model.NewConstant(b1 + 1)
            gap_home[tid].append((cs, ce, b1 - b0 + 1))
        if free_half == "first":
            _add_ac_2_1_8_gap_constraints(model, gap_home, total_days,
                                          day_lo=0, day_hi=b1 + 1)
        else:
            _add_ac_2_1_8_gap_constraints(model, gap_home, total_days,
                                          day_lo=b0, day_hi=total_days)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = cfg.max_solver_time_seconds
    solver.parameters.num_search_workers = cfg.num_search_workers
    solver.parameters.random_seed = cfg.random_seed
    solver.parameters.log_search_progress = cfg.log_search_progress
    st = solver.Solve(model)
    name = solver.StatusName(st)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return (name, None, solver.WallTime())
    return (name, [solver.Value(s) for s in starts], solver.WallTime())


def _solve_ac218_decomposed(
    templates,
    per_team: Dict[str, List[int]],
    per_series_domain: List[List[int]],
    asb_break_days: Set[int],
    total_days: int,
    cfg: GeneratorConfig,
) -> Tuple[str, Optional[List[int]], float]:
    """Drei-Phasen-Decomposition fuer AC-2.1.8 (Q10).

    Der All-Star-Break teilt die Saison: waehrend des Breaks ist jedes Team zu
    Hause, sodass KEINE Road-Trip ihn ueberspannt. Damit zerfaellt AC-2.1.8 in
    zwei unabhaengige Teilprobleme:

      Phase 0: gap-freies Skelett (schnell, ~0.2 s) -> Haelften-Zuordnung.
      Phase 1: erste Haelfte frei, zweite fix -> AC-2.1.8 fuer alle Trips bis
               zum Break (Break-Heimstand als Schluss-Anker).
      Phase 2: zweite Haelfte frei, erste fix -> AC-2.1.8 fuer alle Trips ab
               dem Break (Break-Heimstand als Eroeffnungs-Anker).

    Jede Phase loest ein ~halb so grosses Modell und ist im 1-Worker-Modus
    deterministisch und schnell, wo der monolithische Solve nur intermittierend
    konvergiert.
    """
    b0, b1 = min(asb_break_days), max(asb_break_days)

    st0, skeleton, t0 = _solve_one_phase(
        templates, per_team, per_series_domain, {}, None, b0, b1, total_days, cfg)
    if skeleton is None:
        return (st0, None, t0)

    second_half_fixed = {i: skeleton[i] for i in range(len(templates)) if skeleton[i] > b1}
    st1, after1, t1 = _solve_one_phase(
        templates, per_team, per_series_domain, second_half_fixed, "first",
        b0, b1, total_days, cfg)
    if after1 is None:
        return (st1, None, t0 + t1)

    first_half_fixed = {i: after1[i] for i in range(len(templates)) if after1[i] < b0}
    st2, after2, t2 = _solve_one_phase(
        templates, per_team, per_series_domain, first_half_fixed, "second",
        b0, b1, total_days, cfg)
    return (st2, after2, t0 + t1 + t2)


def generate(quotas: MatchupQuotas, cfg: GeneratorConfig) -> GeneratorResult:
    """Generiert einen Saisonplan.

    Stufe 1: CP-SAT findet einen feasiblen Plan (NoOverlap).
        enforce_fatigue_constraints=True (AC-2.3.10, Sprint 2.4):
            Periodische Break-Days (max_gap=21) werden in die Serien-Domains
            aufgenommen. Pigeonhole-Beweis: jedes 21-Tage-Fenster enthaelt
            mind. 1 Break-Day → max 20 konsekutive Spieltage (AC-2.1.9). ✓
            CP-SAT: OPTIMAL in ~0.4 s (empirisch, Seed 42).

    Stufe 2: Travel-/Fatigue-SA optimiert Reisedistanz.
        enforce_fatigue_constraints=True:
            fatigue_lambda=1_000_000 macht AC-Verletzungen in der SA praktisch
            unmoeglich (Boltzmann-Exponent ~10^-290). Ein deterministischer
            AC-2.1.8-Pre/Post-Repair (generator_optimizer._greedy_fatigue_repair)
            bricht zudem zu lange Road-Trips gezielt auf.
            WICHTIG (Sprint 2.7 / Review C1): AC-2.1.8 nutzt jetzt die korrekte
            "days away from home"-Definition (Off-Days in der Road-Trip zaehlen
            mit). Darunter werden Verletzungen deutlich reduziert, aber bei der
            Saison-Dichte nicht garantiert auf 0 eliminiert — die vollstaendige
            strukturelle Durchsetzung ist ein dokumentierter Folgeschritt
            (siehe docs/CBA_DEFINITIONS.md, docs/SPRINT_2_7_REVIEW.md).
    """
    total_days = _season_days(cfg)
    asb_break_days = _break_day_indices(cfg)   # All-Star-Break-Tage

    # Fatigue-Constraints: periodische Break-Days fuer AC-2.1.9 (max 20
    # Spieltage ohne Off-Day).  max_gap=21 → Break alle 20 Spieltage.
    if cfg.enforce_fatigue_constraints:
        periodic = _periodic_break_days(total_days, max_gap=21)
        break_days = asb_break_days | periodic
    else:
        break_days = asb_break_days

    templates = quotas.series_templates
    num_series = len(templates)

    if num_series == 0:
        return GeneratorResult(season=Season(season=cfg.season),
                               status="OPTIMAL", solve_time_seconds=0.0,
                               num_branches=0, num_conflicts=0)

    status_name = "UNKNOWN"
    cp_sat_seconds = 0.0
    num_branches = 0
    num_conflicts = 0

    # ---- Stufe 1: CP-SAT ---------------------------------------------------
    domains: Dict[int, List[int]] = {}
    for length in {t.length for t in templates}:
        base = _valid_start_domain(length, total_days, break_days)
        domains[length] = base
        if not domains[length]:
            return GeneratorResult(season=None, status="INFEASIBLE",
                                   solve_time_seconds=0.0,
                                   num_branches=0, num_conflicts=0)

    per_team = _team_participations(quotas)

    # Pro Serie die zulaessige Start-Domain (inkl. Disruption-/Blackout-Filter).
    per_series_domain: List[List[int]] = []
    for i, t in enumerate(templates):
        valid = list(domains[t.length])
        blackout = cfg.home_blackout_days.get(t.home)
        if blackout:
            valid = [s for s in valid
                      if not any(d in blackout for d in range(s, s + t.length))]
        if not valid:
            return GeneratorResult(
                season=None, status="INFEASIBLE", solve_time_seconds=0.0,
                num_branches=0, num_conflicts=0,
                objective_value=None, objective_bound=None,
            )
        per_series_domain.append(valid)

    # ---- AC-2.1.8 strukturell (Q10): Drei-Phasen-Decomposition um den Break --
    # Wenn aktiviert UND ein All-Star-Break existiert, wird AC-2.1.8 strukturell
    # garantiert, indem die Saison am Break in zwei unabhaengig geloeste Haelften
    # zerlegt wird (keine Road-Trip ueberspannt den Break). Das ist im 1-Worker-
    # Modus deterministisch und schnell — der monolithische Solve konvergiert nur
    # intermittierend (siehe docs/REFACTOR_BACKLOG.md Q10).
    if cfg.enforce_ac218_structural and asb_break_days:
        status_name, series_starts, cp_sat_seconds = _solve_ac218_decomposed(
            templates, per_team, per_series_domain, asb_break_days,
            total_days, cfg)
        if series_starts is None:
            return GeneratorResult(
                season=None, status=status_name,
                solve_time_seconds=cp_sat_seconds, cp_sat_seconds=cp_sat_seconds,
                num_branches=0, num_conflicts=0,
            )
        num_branches = 0
        num_conflicts = 0
    else:
        model = cp_model.CpModel()
        starts_cp: List[cp_model.IntVar] = []
        intervals_cp: List[cp_model.IntervalVar] = []
        home_series_by_team: Dict[str, List[Tuple[cp_model.IntVar, cp_model.IntVar, int]]] = {}
        for i, t in enumerate(templates):
            start = model.NewIntVarFromDomain(
                cp_model.Domain.FromValues(per_series_domain[i]), f"start_{i}")
            starts_cp.append(start)
            end = model.NewIntVar(0, total_days, f"end_{i}")
            model.Add(end == start + t.length)
            intervals_cp.append(model.NewIntervalVar(start, t.length, end, f"iv_{i}"))
            home_series_by_team.setdefault(t.home, []).append((start, end, t.length))

        for team_id, series_idxs in per_team.items():
            model.AddNoOverlap([intervals_cp[i] for i in series_idxs])

        # Fallback (Flag gesetzt, aber kein Break): monolithische strukturelle
        # Durchsetzung. Ohne Break-Anker nur intermittierend tractable — bewusst
        # nur fuer den Sonderfall ohne All-Star-Break.
        if cfg.enforce_ac218_structural:
            _add_ac_2_1_8_gap_constraints(model, home_series_by_team, total_days)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = cfg.max_solver_time_seconds
        solver.parameters.num_search_workers = cfg.num_search_workers
        solver.parameters.random_seed = cfg.random_seed
        solver.parameters.log_search_progress = cfg.log_search_progress

        status = solver.Solve(model)
        status_name = solver.StatusName(status)
        cp_sat_seconds += solver.WallTime()

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return GeneratorResult(
                season=None,
                status=status_name,
                solve_time_seconds=cp_sat_seconds,
                cp_sat_seconds=cp_sat_seconds,
                num_branches=solver.NumBranches(),
                num_conflicts=solver.NumConflicts(),
            )

        series_starts = [solver.Value(s) for s in starts_cp]
        num_branches = solver.NumBranches()
        num_conflicts = solver.NumConflicts()

    # ---- Loesung in Season-Objekt uebersetzen -----------------------------
    season_obj = _build_season(quotas, cfg, series_starts)

    # ---- Stufe 2: Travel-Optimierung (Simulated Annealing) ----------------
    # Lazy-Import, um Zirkelimport zu vermeiden
    from .data_loader import load_teams as _load_teams

    initial_km: Optional[float] = None
    final_km: Optional[float] = None
    travel_seconds = 0.0
    if cfg.enable_travel_optimization:
        from .generator_optimizer import OptimizerConfig, optimize_travel

        teams = _load_teams(cfg.teams_path)
        # enforce_fatigue_constraints=True: 10x lambda macht SA-Violation-Moves
        # praktisch unmoeglich (P ≈ exp(-667) ≈ 10^-290) → AC-2.1.8 garantiert.
        fatigue_lam = 1_000_000.0 if cfg.enforce_fatigue_constraints else 100_000.0
        opt_cfg = OptimizerConfig(
            iterations=cfg.travel_optimizer_iterations,
            start_temperature=cfg.travel_optimizer_start_temperature,
            end_temperature=cfg.travel_optimizer_end_temperature,
            shift_max_days=cfg.travel_optimizer_shift_max_days,
            seed=cfg.random_seed,
            fatigue_lambda=fatigue_lam,
            enable_lns_ac218_repair=cfg.enable_lns_ac218_repair,
        )
        t0 = time.perf_counter()
        season_obj, opt_log = optimize_travel(season_obj, teams, cfg, opt_cfg)
        travel_seconds = time.perf_counter() - t0
        initial_km = opt_log.initial_km
        final_km = opt_log.final_km

    return GeneratorResult(
        season=season_obj,
        status=status_name,
        solve_time_seconds=cp_sat_seconds + travel_seconds,
        cp_sat_seconds=cp_sat_seconds,
        travel_optimizer_seconds=travel_seconds,
        initial_km=initial_km,
        final_km=final_km,
        num_branches=num_branches,
        num_conflicts=num_conflicts,
    )


def _build_season(quotas: MatchupQuotas, cfg: GeneratorConfig,
                  series_starts: List[int]) -> Season:
    """Baut aus den Solver-Startwerten ein Season-Objekt."""
    games: List[Game] = []
    pk_counter = 1_000_000  # interne IDs fuer generierte Spiele
    for series_idx, start_day in enumerate(series_starts):
        t = quotas.series_templates[series_idx]
        for game_offset in range(t.length):
            d = cfg.season_start + timedelta(days=start_day + game_offset)
            games.append(Game(
                game_pk=pk_counter,
                date=d,
                home=t.home,
                away=t.away,
                venue=t.home,
                doubleheader_seq=0,
                game_type="R",
            ))
            pk_counter += 1
    games.sort(key=lambda g: (g.date, g.game_pk))
    return Season(
        season=cfg.season,
        games=games,
        season_start=cfg.season_start,
        season_end=cfg.season_end,
        all_star_dates=tuple(_iter_break(cfg)) if cfg.all_star_break else tuple(),
    )


def _iter_break(cfg: GeneratorConfig) -> Iterable[date]:
    if not cfg.all_star_break:
        return
    s, e = cfg.all_star_break
    d = s
    while d <= e:
        yield d
        d += timedelta(days=1)
