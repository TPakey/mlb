"""Globaler BoolVar-HAP-Solver (alle Teams simultan, Pair-Matching) (A20-Split)."""
from __future__ import annotations

import logging

logger = logging.getLogger("mlb.column_generation")

from dataclasses import dataclass
from typing import Dict, List, Set

from ortools.sat.python import cp_model

from ..two_phase_pacing import (
    AC_2_1_8_MAX_AWAY_STREAK,
    AC_2_1_9_MAX_GAMES,
    AC_2_1_9_WINDOW_DAYS,
)


@dataclass
class GlobalHAPResult:
    """Ergebnis des globalen HAP-Solvers."""
    status: str                        # "OPTIMAL", "FEASIBLE", "INFEASIBLE"
    patterns: Dict[str, List[str]]     # team_id -> marks-Liste ('H'/'A'/'O')
    solve_time_s: float
    violations: List[str]


def solve_global_hap(
    team_ids: List[str],
    n_home: int,
    n_away: int,
    total_days: int,
    break_days: Set[int],
    seed: int = 42,
    solver_time_limit_s: float = 60.0,
    verbose: bool = True,
) -> GlobalHAPResult:
    """Loest HAP-Zuweisung fuer alle Teams simultan mit globalem CP-SAT-Modell.

    Garantiert:
    - Pair-Matching: an jedem Tag |home_teams| == |away_teams|
    - Pro Team: genau n_home Heimspiele, n_away Auswaertsspiele
    - AC-2.1.8: max 13 konsekutive Auswaerts-Tage
    - AC-2.1.9: max 20 Spieltage in 21-Tage-Fenster
    - Series-Laenge: min 2, max 4 (strukturelle Validitaet fuer Phase B)
    - Kein Spieltag an break_days
    """
    import time
    from collections import Counter

    t0 = time.time()
    n_teams = len(team_ids)
    model = cp_model.CpModel()

    # ── Variablen ──────────────────────────────────────────────────────────
    # plays[t][d] = 1 wenn Team t an Tag d spielt (H oder A)
    # home[t][d]  = 1 wenn Team t an Tag d Heimspiel hat
    plays: List[List[cp_model.IntVar]] = []
    home:  List[List[cp_model.IntVar]] = []

    for ti, tid in enumerate(team_ids):
        p_row = []
        h_row = []
        for d in range(total_days):
            if d in break_days:
                # Pausentage: immer 0
                pv = model.NewConstant(0)
                hv = model.NewConstant(0)
            else:
                pv = model.NewBoolVar(f"p_{ti}_{d}")
                hv = model.NewBoolVar(f"h_{ti}_{d}")
                # home[d] == 1 impliziert plays[d] == 1
                model.AddImplication(hv, pv)
            p_row.append(pv)
            h_row.append(hv)
        plays.append(p_row)
        home.append(h_row)

    # ── Per-Team-Constraints ───────────────────────────────────────────────
    W_218 = AC_2_1_8_MAX_AWAY_STREAK + 1   # = 14
    W_219 = AC_2_1_9_WINDOW_DAYS           # = 21
    MAX_219 = AC_2_1_9_MAX_GAMES           # = 20

    for ti in range(n_teams):
        # Spielquoten
        model.Add(sum(plays[ti]) == n_home + n_away)
        model.Add(sum(home[ti])  == n_home)

        # AC-2.1.8 (CBA-Definition, siehe docs/CBA_DEFINITIONS.md): in jedem
        # 14-Kalendertage-Fenster muss mindestens 1 Heimspiel liegen, damit die
        # Road-Trip-Spanne (Off-Days INKLUSIVE) <= 13 Tage bleibt.
        # QA Q2: zuvor stand hier die schwaechere Form
        #   sum(home) - sum(plays) >= -13   (== sum(away) <= 13 je Fenster),
        # die nur Auswaerts-SPIELTAGE begrenzte und Off-Days NICHT mitzaehlte —
        # inkonsistent mit dem pricing_subproblem (das bereits sum(home)>=1
        # nutzt) und mit der dokumentierten CBA-Definition. Jetzt einheitlich
        # die starke Form.
        for d in range(total_days - W_218 + 1):
            model.Add(sum(home[ti][d:d+W_218]) >= 1)

        # AC-2.1.9: max 20 Spieltage in 21-Tage-Fenster
        for d in range(total_days - W_219 + 1):
            model.Add(sum(plays[ti][d:d+W_219]) <= MAX_219)

        # Series-Laenge min 2 (H und A separat):
        # Constraint: home[d] - home[d-1] <= home[d+1]
        # Bedeutung: neuer H-Block startet (home[d]=1, home[d-1]=0) → home[d+1]=1
        # Randfaelle beachten:
        # a) d=0 (kein Vorgaenger): home[0] <= home[1]
        # b) d+1 ist Break: home[d] <= home[d-1]  (kein Folgespieltag → Serie darf
        #    hier nicht neu anfangen; letzter Tag vor Break muss Teil einer Serie sein)
        # c) d=total_days-1 (kein Nachfolger): home[d] <= home[d-1]
        # In allen anderen Faellen: standard home[d] - home[d-1] <= home[d+1]

        for d in range(total_days):
            if d in break_days:
                continue

            prev_d = d - 1
            next_d = d + 1

            # Nachfolger
            next_playable = (next_d < total_days and next_d not in break_days)

            if not next_playable:
                # Kein spielbarer Nachfolger → kein Serienstart erlaubt
                # home[d] <= home[d-1]  und  away[d] <= away[d-1]
                if prev_d >= 0 and prev_d not in break_days:
                    model.Add(home[ti][d] <= home[ti][prev_d])
                    model.Add(
                        plays[ti][d] - home[ti][d]
                        <= plays[ti][prev_d] - home[ti][prev_d]
                    )
                # Falls auch kein Vorgaenger: isoliertes Einzelspiel → verbieten
                # (nur moeglich fuer d=0 ohne Nachfolger, wäre total_days=1 → ignorieren)
            elif prev_d < 0 or prev_d in break_days:
                # Kein spielbarer Vorgaenger (Saisonanfang oder nach Break)
                # → Serienstart ist zwingend, min-2: home[d] <= home[d+1]
                model.Add(home[ti][d] <= home[ti][next_d])
                model.Add(
                    plays[ti][d] - home[ti][d]
                    <= plays[ti][next_d] - home[ti][next_d]
                )
            else:
                # Standardfall: home[d] - home[d-1] <= home[d+1]
                model.Add(home[ti][d] - home[ti][prev_d] <= home[ti][next_d])
                model.Add(
                    plays[ti][d] - home[ti][d]
                    - plays[ti][prev_d] + home[ti][prev_d]
                    <= plays[ti][next_d] - home[ti][next_d]
                )

        # Series-Laenge max 4: kein 5-Tage-H-Block, kein 5-Tage-A-Block
        # Formulierung: sum(home[d:d+5]) <= 4  und  sum(away[d:d+5]) <= 4
        for d in range(total_days - 4):
            # Nicht auf Fenster anwenden, die einen Break-Tag enthalten
            # (Break unterbricht ohnehin die Serie)
            if any(dd in break_days for dd in range(d, d + 5)):
                continue
            model.Add(sum(home[ti][d:d+5]) <= 4)
            model.Add(
                sum(plays[ti][d:d+5]) - sum(home[ti][d:d+5]) <= 4
            )

    # ── Pair-Matching: pro Tag: |H-teams| == |A-teams| ────────────────────
    # Formulierung: sum_t (2*home[t][d] - plays[t][d]) == 0 fuer jeden Tag d
    for d in range(total_days):
        if d in break_days:
            continue
        model.Add(
            sum(2 * home[ti][d] - plays[ti][d] for ti in range(n_teams)) == 0
        )

    # ── Symmetry-Breaking: erste Team-Zeile als Anker ─────────────────────
    # (optional, verbessert Loesungszeit, hat keinen Einfluss auf Guetigkeit)

    # ── Solver ────────────────────────────────────────────────────────────
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = solver_time_limit_s
    solver.parameters.random_seed = seed
    solver.parameters.num_search_workers = 8
    solver.parameters.log_search_progress = verbose

    status_code = solver.Solve(model)
    solve_time = time.time() - t0

    status_map = {
        cp_model.OPTIMAL:   "OPTIMAL",
        cp_model.FEASIBLE:  "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.UNKNOWN:   "UNKNOWN",
        cp_model.MODEL_INVALID: "MODEL_INVALID",
    }
    status = status_map.get(status_code, f"CODE_{status_code}")

    if status not in ("OPTIMAL", "FEASIBLE"):
        if verbose:
            logger.info(f"[GlobalHAP] {status} ({solve_time:.1f}s)")
        return GlobalHAPResult(status=status, patterns={}, solve_time_s=solve_time, violations=[])

    # ── Patterns extrahieren ───────────────────────────────────────────────
    patterns: Dict[str, List[str]] = {}
    for ti, tid in enumerate(team_ids):
        marks = []
        for d in range(total_days):
            p_val = solver.Value(plays[ti][d])
            h_val = solver.Value(home[ti][d])
            if p_val == 0:
                marks.append('O')
            elif h_val == 1:
                marks.append('H')
            else:
                marks.append('A')
        patterns[tid] = marks

    # ── Schnell-Validierung ────────────────────────────────────────────────
    violations = []
    for d in range(total_days):
        if d in break_days:
            continue
        n_h = sum(1 for tid in team_ids if patterns[tid][d] == 'H')
        n_a = sum(1 for tid in team_ids if patterns[tid][d] == 'A')
        if n_h != n_a:
            violations.append(f"Tag {d}: {n_h} Heim vs {n_a} Auswaerts")

    if verbose:
        from .series_matching import parse_hap_series
        hap = parse_hap_series(patterns, break_days)
        lens = Counter(s.length for ss in hap.values() for s in ss)
        logger.info(f"[GlobalHAP] {status} ({solve_time:.1f}s)  "
              f"Pair-violations={len(violations)}  "
              f"Series-Laengen={dict(sorted(lens.items()))}")

    return GlobalHAPResult(
        status=status,
        patterns=patterns,
        solve_time_s=solve_time,
        violations=violations,
    )
