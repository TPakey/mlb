"""Column-Generation-Loop: Worker, Log, RMP+Pricing-Iteration (A20-Split)."""
from __future__ import annotations

import logging

logger = logging.getLogger("mlb.column_generation")

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .patterns import Pattern, pacing_to_pattern
from .rmp import RMPSolution, solve_rmp
from .pricing import PricingResult, pricing_subproblem
from ..two_phase_pacing import plan_team_pacing


# ====================================================================
# Thread-Worker-Funktionen fuer parallele Phase-A und Pricing
# (ThreadPoolExecutor: CP-SAT gibt die GIL frei → echte Parallelitaet)
# ====================================================================

def _gen_one_pattern_worker(args: tuple) -> Optional[Pattern]:
    """Thread-Worker: generiert ein einzelnes Phase-A-Pattern.

    args = (team_id, n_games, n_home, total_days, break_days, seed, randomize_obj)
    CP-SAT gibt die GIL frei, daher laufen mehrere Aufrufe wirklich parallel.
    """
    tid, n_games, n_home, total_days, break_days, seed, randomize = args
    pacing = plan_team_pacing(
        tid, n_games, n_home, total_days, break_days,
        random_seed=seed,
        randomize_objective=randomize,
        max_solver_time_seconds=0.5,  # Kurz: FEASIBLE reicht fuer init
    )
    if pacing is None:
        return None
    return pacing_to_pattern(pacing, total_days)


def _price_one_team_worker(args: tuple) -> PricingResult:
    """Thread-Worker: loest das Pricing-Subproblem fuer ein Team.

    args = (team_id, n_home, n_away, total_days, break_days,
            dual_team, dual_day, max_solver_time_seconds, random_seed)
    """
    (team_id, n_home, n_away, total_days, break_days,
     dual_team, dual_day, max_solver_time_seconds, random_seed) = args
    return pricing_subproblem(
        team_id=team_id,
        n_home=n_home,
        n_away=n_away,
        total_days=total_days,
        break_days=break_days,
        dual_team=dual_team,
        dual_day=dual_day,
        max_solver_time_seconds=max_solver_time_seconds,
        random_seed=random_seed,
    )


# ====================================================================
# Column-Generation-Loop
# ====================================================================

@dataclass
class ColumnGenerationLog:
    iterations: int
    final_rmp_objective: float
    patterns_added: int
    patterns_per_team: Dict[str, int]
    converged: bool
    # Detailliertes pro-Iteration-Log fuer Diagnose:
    iteration_log: List[dict] = field(default_factory=list)


def run_column_generation(
    teams_meta: Dict[str, Tuple[int, int]],   # team_id -> (n_home, n_away)
    total_days: int,
    break_days: Set[int],
    max_iterations: int = 100,
    pricing_solver_seconds: float = 5.0,
    initial_pattern_seed: int = 42,
    verbose: bool = True,
    initial_patterns_per_team: int = 10,
    objective_improvement_tol: float = 1e-8,
    n_workers: Optional[int] = None,
) -> Tuple[Dict[str, List[Pattern]], RMPSolution, ColumnGenerationLog]:
    """Hauptloop: iteriere RMP + Pricing bis Konvergenz.

    Mit Big-M=1.0 in solve_rmp() und SCALE=100_000 im Pricing sind die
    Konvergenz-Signale numerisch sauber. Schluessel-Parameter:
    - initial_patterns_per_team: mehr = besserer Start-Pool = schnellere Konvergenz
    - pricing_solver_seconds: Jonas hat explizit OK gegeben, laenger zu warten
    - objective_improvement_tol: stoppe wenn RMP-Objective sich nicht mehr verbessert
    - n_workers: Anzahl paralleler Pricing-Worker. None = CPU-Anzahl.
      Paralleles Pricing reduziert Iterationszeit von 30*5s auf ~5s.
    """
    import os
    n_proc = n_workers or os.cpu_count() or 4

    # ---- Parallele Initial-Pool-Generierung ----
    # Phase A loest pro Team in ~1s (mit randomize_objective). Seriell waere
    # das 30 Teams × 10 Patterns × 1s = 300s. Parallel: ~10s total.
    if verbose:
        logger.info(f"[CG] Generating initial patterns: {initial_patterns_per_team}/team "
              f"x {len(teams_meta)} teams (parallel, {n_proc} workers) ...")

    # Alle (team, seed)-Paare als Batch vorbereiten.
    # Wir generieren initial_patterns_per_team + 3 Kandidaten pro Team
    # (kleiner Buffer fuer Dedup-Faelle). Mit randomize_objective=True sind
    # fast alle Kandidaten einzigartig, also reicht ein kleiner Puffer.
    INIT_SEED_BUFFER = 3
    init_args = []
    for tid, (n_home, n_away) in teams_meta.items():
        for s in range(initial_patterns_per_team + INIT_SEED_BUFFER):
            init_args.append((
                tid, n_home + n_away, n_home, total_days, break_days,
                initial_pattern_seed + s * 13,  # diverse seeds
                True,   # randomize_objective
            ))

    # ---- Parallele Initial-Pool-Generierung mit ThreadPoolExecutor ----
    # CP-SAT gibt die GIL frei → echte Parallelitaet mit Python-Threads.
    # Kein spawn/fork-Problem, kein Pickle-Problem, keine PATH-Probleme.
    with ThreadPoolExecutor(max_workers=n_proc) as executor:
        raw_patterns: List[Optional[Pattern]] = list(
            executor.map(_gen_one_pattern_worker, init_args)
        )

    # Dedup pro Team: nimm die ersten `initial_patterns_per_team` einzigartigen
    pattern_pool: Dict[str, List[Pattern]] = {tid: [] for tid in teams_meta}
    seen_per_team: Dict[str, Set[str]] = {tid: set() for tid in teams_meta}
    for pat in raw_patterns:
        if pat is None:
            continue
        tid = pat.team_id
        sig = pat.signature()
        if sig not in seen_per_team[tid] and len(pattern_pool[tid]) < initial_patterns_per_team:
            pattern_pool[tid].append(pat)
            seen_per_team[tid].add(sig)

    for tid in teams_meta:
        if not pattern_pool[tid]:
            raise RuntimeError(f"Phase A INFEASIBLE fuer Team {tid}")

    total_initial = sum(len(v) for v in pattern_pool.values())
    if verbose:
        min_per_team = min(len(v) for v in pattern_pool.values())
        logger.info(f"[CG] Initial pool: {total_initial} patterns total "
              f"(min/team={min_per_team}, target={initial_patterns_per_team})")

    patterns_added = 0
    converged = False
    iterations = 0
    rmp = None
    prev_objective = float("inf")
    iteration_log = []
    stagnant_iters = 0
    MAX_STAGNANT = 15  # Erlaube bis zu 15 degenerierte LP-Pivots

    for it in range(max_iterations):
        iterations = it + 1

        rmp = solve_rmp(pattern_pool, total_days, break_days)
        if rmp.status not in ("OPTIMAL", "FEASIBLE"):
            if verbose:
                logger.info(f"[CG] Iter {it+1}: RMP {rmp.status} — abbruch")
            break

        # Dual-Werte-Diagnose
        active_slacks = sum(1 for d, val in rmp.dual_day.items() if abs(val) > 1e-9)
        dual_range = (min(rmp.dual_day.values(), default=0),
                      max(rmp.dual_day.values(), default=0))

        obj_improvement = prev_objective - rmp.objective
        if verbose:
            logger.info(f"[CG] Iter {it+1:3d}: obj={rmp.objective:.6f}  "
                  f"Δobj={obj_improvement:.6f}  "
                  f"active_days={active_slacks}  "
                  f"duals=[{dual_range[0]:.4f},{dual_range[1]:.4f}]  "
                  f"pool={sum(len(v) for v in pattern_pool.values())}")

        iteration_log.append({
            "iter": it + 1,
            "objective": rmp.objective,
            "delta_obj": obj_improvement,
            "active_slack_days": active_slacks,
            "dual_min": dual_range[0],
            "dual_max": dual_range[1],
            "total_patterns": sum(len(v) for v in pattern_pool.values()),
        })

        # Konvergenz: Slack = 0 (feasible pair-matching!)
        if rmp.objective < 1e-6:
            converged = True
            if verbose:
                logger.info("[CG] ✓ CONVERGED: Pair-Matching feasible (Slack=0)!")
            break

        # Stagnations-Zaehler: LP-Degeneration kann viele Pivots ohne
        # Objective-Verbesserung erzeugen. Erst nach MAX_STAGNANT
        # aufeinanderfolgenden Stagnations-Iterationen aufgeben.
        if it > 0 and obj_improvement < objective_improvement_tol:
            stagnant_iters += 1
            if verbose and stagnant_iters > 1:
                logger.info(f"[CG]   (stagnant {stagnant_iters}/{MAX_STAGNANT})")
            if stagnant_iters >= MAX_STAGNANT:
                if verbose:
                    logger.info(f"[CG] Abbruch nach {MAX_STAGNANT} Stagnations-Iters "
                          f"(obj={rmp.objective:.6f})")
                break
        else:
            stagnant_iters = 0

        prev_objective = rmp.objective

        # ---- Paralleles Pricing: alle Teams gleichzeitig ----
        # Jedes Team bekommt seinen eigenen Pricing-Worker (CP-SAT-Prozess).
        # Wall-Clock-Zeit = max(Einzelzeiten) statt sum(Einzelzeiten).
        # Mit n_proc = CPU-Anzahl: 30 Teams in ~5s statt 150s.
        worker_args = [
            (
                tid,
                n_home, n_away,
                total_days, break_days,
                rmp.dual_team.get(tid, 0.0),
                rmp.dual_day,
                pricing_solver_seconds,
                initial_pattern_seed + it * 7 + i,  # diverser Seed pro Team
            )
            for i, (tid, (n_home, n_away)) in enumerate(teams_meta.items())
        ]

        with ThreadPoolExecutor(max_workers=min(n_proc, len(teams_meta))) as executor:
            pricing_results: List[PricingResult] = list(
                executor.map(_price_one_team_worker, worker_args)
            )

        added_this_iter = 0
        current_sigs = {tid: {p.signature() for p in pats}
                        for tid, pats in pattern_pool.items()}
        for pr in pricing_results:
            if pr.pattern is None:
                continue
            if pr.reduced_cost >= -1e-6:
                continue
            sig = pr.pattern.signature()
            if sig in current_sigs.get(pr.team_id, set()):
                continue
            pattern_pool[pr.team_id].append(pr.pattern)
            current_sigs.setdefault(pr.team_id, set()).add(sig)
            patterns_added += 1
            added_this_iter += 1

        if verbose:
            rc_vals = [pr.reduced_cost for pr in pricing_results if pr.pattern is not None]
            min_rc = min(rc_vals, default=float("inf"))
            logger.info(f"[CG]   → {added_this_iter} neue Patterns  "
                  f"(min_rc={min_rc:.4f})")

        if added_this_iter == 0:
            if verbose:
                logger.info(f"[CG] Kein neues Pattern mit rc<0 — LP-optimal "
                      f"(Slack verbleibend: {rmp.objective:.6f})")
            converged = (rmp.objective < 1e-6)
            break

    log = ColumnGenerationLog(
        iterations=iterations,
        final_rmp_objective=rmp.objective if rmp else 0.0,
        patterns_added=patterns_added,
        patterns_per_team={tid: len(pats) for tid, pats in pattern_pool.items()},
        converged=converged,
        iteration_log=iteration_log,
    )
    return pattern_pool, rmp, log

