"""Phase A des Two-Phase-Schedulers (Sprint 2.3 Task #15).

Pro Team eigenes CP-SAT-Modell, das nur die Tag-Liste plant (welche Tage
spielt das Team, welche Heim, welche Auswaerts). Dieses Modell ist klein
genug (162 IntVars + 162 BoolVars pro Team), dass CP-SAT die Fatigue-
Constraints (AC-2.1.8/9) schnell loesen kann.

Output: pro Team eine sortierte Liste von (day, is_home)-Tupeln. Diese
geht dann in Phase B (Series-Matching) zur Zuordnung der Gegner.

## Diverse-Pattern-Generierung (fuer Column Generation)

Wenn `randomize_objective=True`, wird eine zufaellige lineare Zielfunktion
addiert: Minimize sum(coeff_i * day_vars[i]) + sum(coeff_j * home_vars[j]).
Die Koeffizienten werden aus `random_seed` abgeleitet. Dies zwingt CP-SAT,
verschiedene Teile des Suchraums zu erkunden und liefert diverse Patterns
fuer den Column-Generation-Initialpool.

## Mathematische Formulierung pro Team

Variablen:
- `day[i]` ∈ [0, total_days)  fuer i=0..n_games-1  (sortiert: day[i+1] > day[i])
- `home[i]` ∈ {0, 1}  fuer i=0..n_games-1

Constraints:
1. Distinct + sortiert: day[i+1] > day[i]
2. Saisonfenster: day[i] ∉ break_days
3. Home-Quote: sum(home[i]) = n_home
4. **AC-2.1.9** (max 20 Spieltage in 21 Tagen):
   day[i + 20] - day[i] >= 21  fuer alle i
5. **AC-2.1.8** (max 13 konsekutive Auswaerts-Tage):
   Reified: wenn day[i+13] - day[i] == 13 (= 14 konsekutive Spieltage),
   dann sum(home[i:i+14]) >= 1 (mind. 1 Heimspiel im Block)

Constraint 5 deckt den genauen Streak-Begriff ab: ein "Auswaerts-Streak" ist
eine Folge konsekutiver Tage mit Auswaertsspielen. Ein Off-Day (Day-Diff > 1)
ODER ein Heimspiel unterbricht die Streak.

## Performance

Per Team: 162 IntVars (Domain ~180) + 162 BoolVars + ~10 Sliding-Window-
Constraints. CP-SAT findet typisch in 0.5-3 s pro Team. 30 Teams seriell:
15-90 s total — voll im Charter-Budget (30 min).
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

from ortools.sat.python import cp_model


# AC-Limits
AC_2_1_8_MAX_AWAY_STREAK = 13       # max konsekutive Auswaerts-Tage
AC_2_1_9_WINDOW_DAYS = 21           # Fenstergroesse fuer max-Spieltage
AC_2_1_9_MAX_GAMES = 20             # max Spieltage in 21-Tage-Fenster


@dataclass(frozen=True)
class TeamPacing:
    """Phase-A-Output fuer ein Team."""
    team_id: str
    # Sortierte Liste von (day_idx, is_home)-Tupeln.
    # day_idx ist 0-basiert relativ zu season_start.
    schedule: Tuple[Tuple[int, bool], ...]
    solver_status: str
    solver_seconds: float

    @property
    def n_games(self) -> int:
        return len(self.schedule)

    @property
    def n_home(self) -> int:
        return sum(1 for _, is_h in self.schedule if is_h)

    @property
    def n_away(self) -> int:
        return self.n_games - self.n_home

    def home_days(self) -> List[int]:
        return [d for d, is_h in self.schedule if is_h]

    def away_days(self) -> List[int]:
        return [d for d, is_h in self.schedule if not is_h]


def plan_team_pacing(
    team_id: str,
    n_games: int,
    n_home: int,
    total_days: int,
    break_days: Set[int],
    max_solver_time_seconds: float = 60.0,
    random_seed: int = 42,
    randomize_objective: bool = False,
) -> Optional[TeamPacing]:
    """Plant fuer ein Team eine AC-2.1.8/9-konforme Tag-Liste.

    Args:
        team_id: Team-Identifier (fuer Logging und das Output-Objekt).
        n_games: Gesamtzahl der Spiele des Teams (Heim + Auswaerts).
        n_home: Anzahl der Heimspiele.
        total_days: Saisonlaenge in Tagen.
        break_days: Set von Tag-Indizes, an denen kein Spiel erlaubt ist.
        max_solver_time_seconds: Solver-Budget (Default 60 s).
        random_seed: Seed fuer CP-SAT-Reproduzierbarkeit.

    Returns:
        TeamPacing wenn feasible, None wenn der Solver UNKNOWN/INFEASIBLE
        zurueckliefert.
    """
    model = cp_model.CpModel()

    # ---- Spieltage als sortierte IntVars ----
    # Domain: alle Saisontage außer Break-Tagen
    allowed_days = [d for d in range(total_days) if d not in break_days]
    day_domain = cp_model.Domain.FromValues(allowed_days)
    day_vars: List[cp_model.IntVar] = [
        model.NewIntVarFromDomain(day_domain, f"day_{team_id}_{i}")
        for i in range(n_games)
    ]
    # Strikt sortiert (= distinct, keine Doubleheader im Pacing-Modell)
    for i in range(n_games - 1):
        model.Add(day_vars[i + 1] > day_vars[i])

    # ---- AC-2.1.9: Sliding-Window-Distanz auf den sortierten Tagen ----
    # In jedem 21-Tage-Fenster max 20 Spieltage ⇔
    # 21 aufeinanderfolgende Spiele muessen >=21 Tage spannen
    for i in range(n_games - AC_2_1_9_MAX_GAMES):
        model.Add(
            day_vars[i + AC_2_1_9_MAX_GAMES] - day_vars[i]
            >= AC_2_1_9_WINDOW_DAYS
        )

    # ---- Home/Away-Indikatoren ----
    home_vars: List[cp_model.IntVar] = [
        model.NewBoolVar(f"home_{team_id}_{i}") for i in range(n_games)
    ]
    model.Add(sum(home_vars) == n_home)

    # ---- AC-2.1.8 (Phase-A-Heuristik, NICHT die volle CBA-Spanne) ----
    # QA-Hinweis (2026-05-29): Diese Reified-Logik verbietet NUR den Fall, dass
    # 14 aufeinanderfolgende SPIELE auf 14 aufeinanderfolgenden Kalendertagen
    # liegen (kein Off-Day dazwischen) und alle auswaerts sind. Unter der
    # korrigierten CBA-Definition (Off-Days mitten in der Road-Trip zaehlen MIT,
    # siehe docs/CBA_DEFINITIONS.md) ist das NICHT die einzige Verletzung — eine
    # Road-Trip mit Off-Days kann >13 Kalendertage spannen, ohne hier gefasst zu
    # werden. Das ist in Phase A bewusst akzeptiert: Phase A erzeugt nur einen
    # Start-Pattern-Pool. Die verbindliche AC-2.1.8-Durchsetzung (volle Spanne,
    # sum(home[d:d+14])>=1) liegt downstream im pricing_subproblem und in
    # solve_global_hap. Wer Phase A je als alleinige Quelle nutzt, muss die
    # Spanne dort nachziehen.
    window = AC_2_1_8_MAX_AWAY_STREAK + 1   # 14
    for i in range(n_games - window + 1):
        # Bool: alle window Spiele liegen genau auf konsekutiven Tagen?
        consecutive = model.NewBoolVar(f"consec_{team_id}_{i}")
        model.Add(
            day_vars[i + window - 1] - day_vars[i] == window - 1
        ).OnlyEnforceIf(consecutive)
        model.Add(
            day_vars[i + window - 1] - day_vars[i] != window - 1
        ).OnlyEnforceIf(consecutive.Not())
        # Wenn consecutive, dann muss min. 1 Heim im Block sein
        model.Add(
            sum(home_vars[i:i + window]) >= 1
        ).OnlyEnforceIf(consecutive)

    # ---- Randomisierte Zielobjektfunktion (fuer diverse Pattern-Generierung) ----
    # Ohne Objective findet CP-SAT IMMER dieselbe Loesung (lexikographisch
    # kleinste). Mit einer zufaelligen linearen Zielfunktion wird der Solver
    # gezwungen, verschiedene Regionen des Suchraums zu erkunden.
    # WICHTIG: Diese Objective VERAENDERT NICHT die Gueltigkeit der Loesung
    # (alle AC-2.1.8/9-Constraints bleiben aktiv). Sie bestimmt nur, welche
    # der vielen gueltigen Loesungen gefunden wird.
    if randomize_objective:
        rng = random.Random(random_seed)
        # Koeffizienten fuer Spieltag-Vars (0..999) und Home-Vars (0..999)
        day_coeffs = [rng.randint(0, 999) for _ in range(n_games)]
        home_coeffs = [rng.randint(0, 999) for _ in range(n_games)]
        model.Minimize(
            sum(c * v for c, v in zip(day_coeffs, day_vars))
            + sum(c * v for c, v in zip(home_coeffs, home_vars))
        )

    # ---- Solve ----
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_solver_time_seconds
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = random_seed
    status = solver.Solve(model)
    status_name = solver.StatusName(status)
    wall = solver.WallTime()

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    schedule = tuple(
        (solver.Value(day_vars[i]), bool(solver.Value(home_vars[i])))
        for i in range(n_games)
    )
    return TeamPacing(
        team_id=team_id,
        schedule=schedule,
        solver_status=status_name,
        solver_seconds=wall,
    )


def validate_team_pacing(pacing: TeamPacing) -> List[str]:
    """Verifiziert die Pacing-Output mathematisch (defensiv).

    Liefert eine Liste der Violation-Messages (leer = ok).
    """
    violations: List[str] = []
    if not pacing.schedule:
        return violations
    days = [d for d, _ in pacing.schedule]
    homes = [is_h for _, is_h in pacing.schedule]
    # Sortiert?
    for i in range(len(days) - 1):
        if days[i + 1] <= days[i]:
            violations.append(f"days not strictly sorted at {i}")
    # AC-2.1.9
    for i in range(len(days) - AC_2_1_9_MAX_GAMES):
        gap = days[i + AC_2_1_9_MAX_GAMES] - days[i]
        if gap < AC_2_1_9_WINDOW_DAYS:
            violations.append(
                f"AC-2.1.9 violation at game {i}: 21 games in only {gap} days"
            )
    # AC-2.1.8
    window = AC_2_1_8_MAX_AWAY_STREAK + 1
    for i in range(len(days) - window + 1):
        if days[i + window - 1] - days[i] == window - 1:
            # konsekutive Tage
            if not any(homes[i:i + window]):
                violations.append(
                    f"AC-2.1.8 violation at game {i}: 14 consec away days"
                )
    return violations
