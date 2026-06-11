"""Restricted Master Problem (LP-Relaxierung) der Column Generation (A20-Split)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

from ortools.linear_solver import pywraplp

from .patterns import Pattern


@dataclass
class RMPSolution:
    """Loesung des RMP."""
    status: str            # "OPTIMAL", "FEASIBLE", "INFEASIBLE"
    x_values: Dict[Tuple[str, int], float]   # (team_id, pattern_idx) -> wert
    dual_team: Dict[str, float]              # pro Team: dualer Wert
    dual_day: Dict[int, float]               # pro Tag: dualer Wert (Pair-Matching)
    objective: float


def solve_rmp(
    pattern_pool: Dict[str, List[Pattern]],
    total_days: int,
    break_days: Set[int],
    big_m: float = 1.0,
) -> RMPSolution:
    """Lest das RMP als LP-Relaxierung mit Slack-Variables (Phase-1-Style).

    Da der initiale Pattern-Pool meistens keine feasible Pair-Matching-Loesung
    zulaesst, addieren wir Slack-Variables pro Pair-Matching-Constraint. Die
    Objective minimiert die Slacks (Phase-1-Style), sodass Column Generation
    iterativ Patterns hinzufuegt, die Slacks reduzieren.

    Wenn alle Slacks am Ende = 0 sind, ist die LP-Loesung echt feasible.

    WICHTIG: big_m=1.0 (nicht 1e6!). Mit Big-M = 1e6 wuerden die dualen Werte
    ±1e6 erreichen, was die SCALE-Quantisierung im Pricing-Subproblem
    vollstaendig zerstoert (Praezisionsverlust 99.9%). Mit Big-M = 1 sind die
    Duals garantiert in [-1, 1] und SCALE=100_000 gibt 5 Stellen Praezision.
    """
    solver = pywraplp.Solver.CreateSolver("GLOP")
    if solver is None:
        raise RuntimeError("GLOP-Solver nicht verfuegbar")

    # ---- Variablen: x[team, p_idx] ∈ [0, 1] ----
    x: Dict[Tuple[str, int], pywraplp.Variable] = {}
    for team_id, patterns in pattern_pool.items():
        for p_idx in range(len(patterns)):
            x[(team_id, p_idx)] = solver.NumVar(0.0, 1.0, f"x_{team_id}_{p_idx}")

    # ---- Slack-Variables pro Tag (positiv und negativ, fuer Pair-Matching-Ausgleich) ----
    slack_pos: Dict[int, pywraplp.Variable] = {}
    slack_neg: Dict[int, pywraplp.Variable] = {}
    for d in range(total_days):
        if d in break_days:
            continue
        slack_pos[d] = solver.NumVar(0.0, solver.infinity(), f"sp_{d}")
        slack_neg[d] = solver.NumVar(0.0, solver.infinity(), f"sn_{d}")

    # ---- Team-Constraints: sum_p x[t, p] == 1 ----
    team_constraints: Dict[str, pywraplp.Constraint] = {}
    for team_id, patterns in pattern_pool.items():
        c = solver.Constraint(1.0, 1.0, f"team_{team_id}")
        for p_idx in range(len(patterns)):
            c.SetCoefficient(x[(team_id, p_idx)], 1.0)
        team_constraints[team_id] = c

    # ---- Pair-Matching pro Tag: sum n_home - sum n_away + s+ - s- == 0 ----
    day_constraints: Dict[int, pywraplp.Constraint] = {}
    for d in range(total_days):
        if d in break_days:
            continue
        c = solver.Constraint(0.0, 0.0, f"day_{d}")
        for team_id, patterns in pattern_pool.items():
            for p_idx, pat in enumerate(patterns):
                if pat.is_home_at(d):
                    c.SetCoefficient(x[(team_id, p_idx)], 1.0)
                elif pat.is_away_at(d):
                    c.SetCoefficient(x[(team_id, p_idx)], -1.0)
        # Slack absorbiert Mismatch
        c.SetCoefficient(slack_pos[d], -1.0)
        c.SetCoefficient(slack_neg[d], 1.0)
        day_constraints[d] = c

    # ---- Objective: minimize Big-M * sum(Slacks) ----
    obj = solver.Objective()
    obj.SetMinimization()
    for d in slack_pos:
        obj.SetCoefficient(slack_pos[d], big_m)
        obj.SetCoefficient(slack_neg[d], big_m)

    status = solver.Solve()
    status_name = {
        pywraplp.Solver.OPTIMAL: "OPTIMAL",
        pywraplp.Solver.FEASIBLE: "FEASIBLE",
        pywraplp.Solver.INFEASIBLE: "INFEASIBLE",
        pywraplp.Solver.UNBOUNDED: "UNBOUNDED",
        pywraplp.Solver.ABNORMAL: "ABNORMAL",
        pywraplp.Solver.NOT_SOLVED: "NOT_SOLVED",
    }.get(status, "UNKNOWN")

    if status not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        return RMPSolution(
            status=status_name, x_values={}, dual_team={},
            dual_day={}, objective=0.0,
        )

    # ---- Werte extrahieren ----
    x_vals = {key: var.solution_value() for key, var in x.items()}
    dual_team = {tid: c.dual_value() for tid, c in team_constraints.items()}
    dual_day = {d: c.dual_value() for d, c in day_constraints.items()}

    return RMPSolution(
        status=status_name,
        x_values=x_vals,
        dual_team=dual_team,
        dual_day=dual_day,
        objective=solver.Objective().Value(),
    )
