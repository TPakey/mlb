"""Spielplan-Optimierer mit Simulated Annealing.

Verwendet das Multi-Dimensional Scoring System (siehe scoring.py) und ein
konfigurierbares Tradeoff-Profil (siehe profiles.py).

Warum nicht reines OR-Tools-MIP? Eine vollständige MIP-Formulierung mit
30 Teams × 27 Slots × 30 möglichen Gegnern wäre rechnerisch nur mit
spezialisierten Solvern (Gurobi, CPLEX) und Stunden Laufzeit handhabbar.
Simulated Annealing ist hier pragmatischer:
- läuft in Sekunden,
- akzeptiert nichtlineare Multi-Score-Bewertung nativ,
- erzeugt nachvollziehbare Verbesserungen gegenüber dem Baseline-Plan.

Bewegungen (Neighborhood Moves):
1) HOME-FLIP        — Heim/Auswärts einer einzelnen Serie tauschen
2) INTRA-SLOT-SWAP  — innerhalb desselben Slots zwei Serien rotieren
3) INTER-SLOT-SWAP  — zwischen zwei Slots Partner austauschen
   (alle Moves erhalten "jedes Team genau eine Serie pro Slot")
"""
from __future__ import annotations

import math
import random
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .constraints import validate
from ..data_loader import Team
from ..distance import TravelLeg
from .schedule_generator import Schedule, Series
from .scoring import ScoreBundle, compute_scores, weighted_cost
from .tradeoff_profiles import TradeoffProfile


@dataclass
class OptimizationConfig:
    iterations: int = 6000
    start_temperature: float = 3000.0
    end_temperature: float = 5.0
    seed: int = 7
    log_every: int = 200
    enforce_hard_constraints: bool = True


@dataclass
class OptimizationResult:
    schedule: Schedule
    profile: TradeoffProfile
    initial_bundle: ScoreBundle
    final_bundle: ScoreBundle
    initial_cost: float
    final_cost: float
    history: List[float] = field(default_factory=list)
    accepted_moves: int = 0
    rejected_moves: int = 0
    rejected_for_constraints: int = 0


# ---------------------- Moves ----------------------

def _snapshot(*series: Series) -> dict:
    return {id(s): (s.home, s.away) for s in series}


def _restore(snap: dict, *series: Series) -> None:
    for s in series:
        if id(s) in snap:
            s.home, s.away = snap[id(s)]


def _move_home_flip(sched: Schedule, rng: random.Random) -> Tuple[List[Series], dict]:
    s = rng.choice(sched.series)
    snap = _snapshot(s)
    s.home, s.away = s.away, s.home
    return [s], snap


def _move_intra_slot_swap(sched: Schedule, rng: random.Random) -> Tuple[List[Series], dict]:
    by_slot = sched.by_slot()
    slot = rng.choice(list(by_slot.keys()))
    pool = by_slot[slot]
    if len(pool) < 2:
        return [], {}
    s1, s2 = rng.sample(pool, 2)
    snap = _snapshot(s1, s2)
    # (A,B) + (C,D)  →  (A,C) + (B,D)
    s1.away, s2.away = s2.away, s1.away
    return [s1, s2], snap


def _move_inter_slot_swap(sched: Schedule, teams: List[Team],
                           rng: random.Random) -> Tuple[List[Series], dict]:
    t_choice = rng.choice(teams).id
    my = sorted(sched.for_team(t_choice), key=lambda x: x.slot)
    if len(my) < 2:
        return [], {}
    s1, s2 = rng.sample(my, 2)
    p1 = s1.opponent_of(t_choice)
    p2 = s2.opponent_of(t_choice)
    if p1 == p2:
        return [], {}
    cands_p1 = [x for x in sched.series if x.slot == s2.slot and x.involves(p1)]
    cands_p2 = [x for x in sched.series if x.slot == s1.slot and x.involves(p2)]
    if not cands_p1 or not cands_p2:
        return [], {}
    s3 = cands_p1[0]
    s4 = cands_p2[0]
    q1 = s3.opponent_of(p1)
    q2 = s4.opponent_of(p2)
    if q1 == t_choice or q2 == t_choice:
        return [], {}

    snap = _snapshot(s1, s2, s3, s4)

    def _replace(series: Series, old: str, new: str) -> None:
        if series.home == old:
            series.home = new
        elif series.away == old:
            series.away = new

    _replace(s1, p1, p2)
    _replace(s4, p2, p1)
    _replace(s2, p2, p1)
    _replace(s3, p1, p2)
    return [s1, s2, s3, s4], snap


# ---------------------- Hauptalgorithmus ----------------------

def optimize(schedule: Schedule, teams: List[Team], teams_by_id: Dict[str, Team],
             leg_map: Dict[Tuple[str, str], TravelLeg], soft_factors: dict,
             profile: TradeoffProfile,
             cfg: OptimizationConfig = OptimizationConfig()) -> OptimizationResult:
    rng = random.Random(cfg.seed)
    current = deepcopy(schedule)

    init_bundle = compute_scores(current, teams, teams_by_id, leg_map, soft_factors)
    init_cost = weighted_cost(init_bundle, profile)

    best = deepcopy(current)
    best_bundle = init_bundle
    best_cost = init_cost
    current_cost = init_cost

    history: List[float] = [current_cost]
    accepted = 0
    rejected = 0
    rej_hard = 0

    for it in range(cfg.iterations):
        progress = it / max(1, cfg.iterations - 1)
        T = cfg.start_temperature * (cfg.end_temperature / cfg.start_temperature) ** progress

        r = rng.random()
        if r < 0.20:
            touched, snap = _move_home_flip(current, rng)
        elif r < 0.70:
            touched, snap = _move_intra_slot_swap(current, rng)
        else:
            touched, snap = _move_inter_slot_swap(current, teams, rng)

        if not touched:
            continue

        # Hard-Constraint-Validierung (leichtgewichtige Slot-Invariante)
        if cfg.enforce_hard_constraints:
            rep = validate(current, teams, teams_by_id)
            if not rep.is_valid:
                _restore(snap, *touched)
                rej_hard += 1
                continue

        new_bundle = compute_scores(current, teams, teams_by_id, leg_map, soft_factors)
        new_cost = weighted_cost(new_bundle, profile)
        dE = new_cost - current_cost
        accept = dE < 0 or rng.random() < math.exp(-dE / max(1e-9, T))

        if accept:
            current_cost = new_cost
            accepted += 1
            if new_cost < best_cost:
                best_cost = new_cost
                best_bundle = new_bundle
                best = deepcopy(current)
        else:
            _restore(snap, *touched)
            rejected += 1

        if it % cfg.log_every == 0:
            history.append(current_cost)

    return OptimizationResult(
        schedule=best,
        profile=profile,
        initial_bundle=init_bundle,
        final_bundle=best_bundle,
        initial_cost=init_cost,
        final_cost=best_cost,
        history=history,
        accepted_moves=accepted,
        rejected_moves=rejected,
        rejected_for_constraints=rej_hard,
    )
