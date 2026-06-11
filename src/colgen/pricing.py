"""Pricing-Subproblem (CP-SAT) der Column Generation (A20-Split)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from ortools.sat.python import cp_model

from .patterns import Pattern
from ..two_phase_pacing import (
    AC_2_1_8_MAX_AWAY_STREAK,
    AC_2_1_9_MAX_GAMES,
    AC_2_1_9_WINDOW_DAYS,
)


@dataclass
class PricingResult:
    """Ergebnis eines Pricing-Subproblems pro Team."""
    team_id: str
    pattern: Optional[Pattern]
    reduced_cost: float
    status: str
    solver_seconds: float


def pricing_subproblem(
    team_id: str,
    n_home: int,
    n_away: int,
    total_days: int,
    break_days: Set[int],
    dual_team: float,
    dual_day: Dict[int, float],
    max_solver_time_seconds: float = 10.0,
    random_seed: int = 42,
) -> PricingResult:
    """Generiert ein Pattern mit minimalen reduzierten Kosten fuer ein Team.

    ## BoolVar-Formulierung (direkte lineare Objective, kein AddElement)

    Variablen: pro Tag d zwei BoolVars:
    - plays[d] = 1 wenn Team an Tag d spielt (Heim oder Auswaerts)
    - home[d]  = 1 wenn Team an Tag d Heimspiel hat

    Constraints:
    1. Break-Tage: plays[d] = 0
    2. home[d] <= plays[d] (Heimspiel erfordert Spieltag)
    3. sum(plays) = n_games, sum(home) = n_home
    4. AC-2.1.9: sum(plays[d:d+21]) <= 20 (Sliding-Window, linear)
    5. AC-2.1.8: sum(home[d:d+W]) - sum(plays[d:d+W]) >= -(W-1)
       fuer Fenstergroesse W = 14. Prueft: wenn alle W Tage gespielt
       werden (sum_plays=W), muss mind. 1 Heimspiel dabei sein (sum_home>=1).
       Linear herleitbar: h - p >= -(W-1)  iff  h >= p - (W-1)  iff
       h + (W - p) >= 1  (mindestens ein "nicht-Auswärts"-Beitrag).

    Reduced-Cost-Objective (DIREKT LINEAR — kein AddElement):
      minimize: -sum_d dual_day[d] * (2*home[d] - plays[d])
      = minimize: sum_d int_dual[d] * (plays[d] - 2*home[d])

    Wenn Objective-Wert = obj_scaled, dann:
      contribution_sum = -obj_scaled / SCALE
      rc = -dual_team - contribution_sum = -dual_team + obj_scaled / SCALE

    Vorteil gegenueber IntVar-Formulierung: kein AddElement, keine
    Reified-Hilfsvariablen. Modell: ~372 BoolVars, ~700 lineare Constraints.
    CP-SAT loest das in << 1s (vs. 5s+ mit AddElement-Formulierung).
    """
    n_games = n_home + n_away

    # Skalierung: Big-M=1.0 → dual_day ∈ [-1,1] → int-Werte in [-SCALE, SCALE]
    SCALE = 100_000
    dual_day_int: List[int] = [
        int(round(dual_day.get(d, 0.0) * SCALE)) for d in range(total_days)
    ]

    model = cp_model.CpModel()

    # ---- BoolVars: plays[d] und home[d] fuer jeden Saisontag ----
    plays: List[cp_model.IntVar] = [
        model.NewBoolVar(f"p_{d}") for d in range(total_days)
    ]
    home: List[cp_model.IntVar] = [
        model.NewBoolVar(f"h_{d}") for d in range(total_days)
    ]

    # Break-Tage: kein Spiel
    for d in break_days:
        model.Add(plays[d] == 0)

    # home[d] <= plays[d]
    for d in range(total_days):
        model.Add(home[d] <= plays[d])

    # Gesamt-Spieltage und Heimspiele
    model.Add(sum(plays) == n_games)
    model.Add(sum(home) == n_home)

    # ---- AC-2.1.9: max 20 Spieltage in jedem 21-Tage-Kalender-Fenster ----
    # sum(plays[d : d+21]) <= 20  fuer alle d
    window_2_1_9 = AC_2_1_9_WINDOW_DAYS  # 21
    max_2_1_9 = AC_2_1_9_MAX_GAMES       # 20
    for d in range(total_days - window_2_1_9 + 1):
        model.Add(sum(plays[d: d + window_2_1_9]) <= max_2_1_9)

    # ---- AC-2.1.8: max 13 "days away from home" (CBA-Definition) ----
    # Korrekte Definition (siehe docs/CBA_DEFINITIONS.md): Eine Road-Trip ist
    # ein zusammenhaengender Block von Kalendertagen ohne Heimspiel; Off-Days
    # mitten in der Reise zaehlen MIT. Eine Road-Trip darf hoechstens 13 Tage
    # dauern -> in jedem Fenster von (13+1)=14 aufeinanderfolgenden Kalender-
    # tagen muss mindestens ein Heimspiel liegen:
    #   sum(home[d : d+14]) >= 1   fuer alle d
    # Damit kann es keine 14 aufeinanderfolgenden Tage ohne Heimspiel geben,
    # die Road-Trip-Spanne bleibt also <= 13 Kalendertage. (Off-Days zaehlen
    # automatisch mit, weil sie das Heim-Fenster nicht fuellen.)
    window_2_1_8 = AC_2_1_8_MAX_AWAY_STREAK + 1  # 14
    for d in range(total_days - window_2_1_8 + 1):
        model.Add(sum(home[d: d + window_2_1_8]) >= 1)

    # ---- Objective: minimize sum_d int_dual[d] * (plays[d] - 2*home[d]) ----
    # Entspricht: minimize -sum_d dual[d] * (2*home[d] - plays[d])
    #           = minimize -contribution_sum * SCALE
    # Reduzierte Kosten: rc = -dual_team + obj_scaled / SCALE
    obj_terms = []
    for d in range(total_days):
        mu = dual_day_int[d]
        if mu != 0:
            obj_terms.append(mu * plays[d])
        if mu != 0:
            obj_terms.append(-2 * mu * home[d])
    if obj_terms:
        model.Minimize(sum(obj_terms))

    # ---- Solve ----
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_solver_time_seconds
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = random_seed
    status = solver.Solve(model)
    status_name = solver.StatusName(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return PricingResult(
            team_id=team_id, pattern=None, reduced_cost=float("inf"),
            status=status_name, solver_seconds=solver.WallTime(),
        )

    # Pattern aus BoolVars extrahieren
    marks = ['O'] * total_days
    for d in range(total_days):
        if solver.Value(plays[d]):
            marks[d] = 'H' if solver.Value(home[d]) else 'A'

    # Reduced Cost berechnen
    obj_scaled = solver.ObjectiveValue()
    contribution_sum = -obj_scaled / SCALE
    reduced_cost = -dual_team - contribution_sum

    return PricingResult(
        team_id=team_id,
        pattern=Pattern(team_id=team_id, marks=tuple(marks)),
        reduced_cost=reduced_cost,
        status=status_name,
        solver_seconds=solver.WallTime(),
    )


