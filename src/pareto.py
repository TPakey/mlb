"""Pareto-Sampling-Engine (Sprint 2.3b Phase 4).

Orchestriert die vollständige Pareto-Front-Berechnung über alle 8
Score-Dimensionen des ParetoBundle.

Algorithmus:
1. **Anker-Pläne** (6 named Profiles): Jedes Profil betont eine andere
   Dimension. Die SA findet für jedes Profil das lokale Optimum.
2. **Interpolierte Pläne** (optional): Zufällige Konvexkombinationen der
   Anchor-Gewichte erzeugen weitere Streu-Punkte im Inneren der Frontier.
3. **Dominanz-Filter**: Entfernt dominierte Pläne.
4. Gibt ≥ N_MIN_NON_DOMINATED nicht-dominierte ParetoPoints zurück.

Design-Entscheidungen:
- Alle SA-Läufe starten vom selben Baseline-Plan → keine HAP/Phase-B-
  Wiederholung pro Run; spart 23s × N_profiles.
- Deterministisch: Seed-Derivation = master_seed + run_index.
- Constraint-Verletzungen werden gefiltert (is_valid() muss True sein).
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Audit A17 (Sprint A-3): strukturiertes Logging.
logger = logging.getLogger("mlb.pareto")

from .data_loader import Team
from .event_conflicts import LocalEvent, load_local_events
from .generator import GeneratorConfig
from .generator_optimizer import optimize_pareto
from .pareto_types import ParetoPoint
from .profiles import ParetoProfile, PARETO_PROFILES
from .revenue import RevenueModel
from .season import Season
from .tv_slots import TvSlotConfig


N_MIN_NON_DOMINATED = 7    # AC-2.3.1


# ====================================================================
# ParetoFrontier — Ergebnis-Container
# ====================================================================

@dataclass
class ParetoFrontier:
    """Vollständige Ergebnis-Struktur der Pareto-Sampling-Engine."""
    points: List[ParetoPoint]             # alle nicht-dominierten Punkte
    all_evaluated: List[ParetoPoint]      # alle Punkte inkl. dominierter
    anchor_labels: List[str]              # welche Punkte sind Anker
    total_wall_time_s: float
    n_profiles_run: int
    master_seed: int
    # M6 (Sprint 2.11): Diagnose, falls keine constraint-freie Lösung gefunden
    # wurde und ein Least-Bad-Fallback verwendet werden musste.
    degraded: bool = False
    diagnostic: str = ""

    @property
    def n_non_dominated(self) -> int:
        return len(self.points)

    def best_by(self, dimension: str) -> Optional[ParetoPoint]:
        """Gibt den Punkt zurück, der auf einer Dimension am besten ist.

        Liefert None, wenn die Frontier leer ist (M6) — Aufrufer müssen das
        behandeln, statt auf einem ValueError aus min/max([]) zu laufen.
        """
        dir_map = {
            "travel_km":         (lambda p: p.bundle.travel_km,        True),   # min
            "revenue_usd":       (lambda p: p.bundle.revenue_usd,      False),  # max
            "fatigue_score":     (lambda p: p.bundle.fatigue_score,    True),
            "max_away_streak":   (lambda p: p.bundle.max_away_streak,  True),
            "off_day_variance":  (lambda p: p.bundle.off_day_variance, True),
            "tv_slot_score":     (lambda p: p.bundle.tv_slot_score,    False),  # max
            "event_friction":    (lambda p: p.bundle.event_friction,   True),
        }
        if dimension not in dir_map:
            raise ValueError(f"Unbekannte Dimension: {dimension}")
        if not self.points:
            return None
        key_fn, minimize = dir_map[dimension]
        return min(self.points, key=key_fn) if minimize else max(self.points, key=key_fn)

    def to_dict(self) -> Dict:
        return {
            "n_non_dominated": self.n_non_dominated,
            "total_wall_time_s": self.total_wall_time_s,
            "n_profiles_run": self.n_profiles_run,
            "master_seed": self.master_seed,
            "anchor_labels": self.anchor_labels,
            "points": [
                {
                    "label": p.label,
                    "profile_used": p.profile_used,
                    "seed_used": p.seed_used,
                    "bundle": p.bundle.to_dict(),
                }
                for p in self.points
            ],
        }


# ====================================================================
# Dominanz-Filter
# ====================================================================

def filter_dominated(points: List[ParetoPoint]) -> List[ParetoPoint]:
    """Entfernt alle dominierten Punkte.

    A dominiert B, wenn A in allen Dimensionen ≤ B ist (kleiner = besser)
    und mindestens in einer Dimension strikt besser.

    O(N²) — für N ≤ 50 Pläne völlig ausreichend.
    Nur valide Pläne (constraint_violations == 0) werden berücksichtigt.
    """
    valid = [p for p in points if p.bundle.is_valid()]
    non_dom: List[ParetoPoint] = []
    for i, cand in enumerate(valid):
        dominated = False
        for j, other in enumerate(valid):
            if i == j:
                continue
            if other.bundle.dominates(cand.bundle):
                dominated = True
                break
        if not dominated:
            non_dom.append(cand)
    return non_dom


# ====================================================================
# Profil-Interpolation für Interior-Punkte
# ====================================================================

def _interpolate_profile(p1: ParetoProfile, p2: ParetoProfile,
                           t: float, name: str = "interior") -> ParetoProfile:
    """Lineare Interpolation zwischen zwei ParetoProfilen.

    t=0 → p1, t=1 → p2, t=0.5 → Mittelpunkt.
    """
    def lerp(a: float, b: float) -> float:
        return a * (1 - t) + b * t

    return ParetoProfile(
        name=name,
        description=f"Interpoliert zwischen {p1.name} und {p2.name} (t={t:.2f})",
        w_travel      = lerp(p1.w_travel,       p2.w_travel),
        w_revenue     = lerp(p1.w_revenue,      p2.w_revenue),
        w_fatigue     = lerp(p1.w_fatigue,      p2.w_fatigue),
        w_away_streak = lerp(p1.w_away_streak,  p2.w_away_streak),
        w_off_day     = lerp(p1.w_off_day,      p2.w_off_day),
        w_tv          = lerp(p1.w_tv,           p2.w_tv),
        w_friction    = lerp(p1.w_friction,     p2.w_friction),
    )


def _random_profile(rng: random.Random, name: str = "random",
                     alpha: float = 1.0) -> ParetoProfile:
    """Zufälliges ParetoProfile als gewichtete Mischung aller Anker.

    N5 (Sprint 2.11): Echtes Dirichlet-Sampling statt `random()/sum`. Letzteres
    (Uniform-auf-Summe-normiert) konzentriert die Gewichte in der Simplex-Mitte.
    Dirichlet(alpha=1) liefert dagegen eine *uniforme* Verteilung über das
    Simplex — bessere Abdeckung der Profil-Mischungen für die Pareto-Diversität.
    Realisiert über Gamma-Variates: x_i ~ Gamma(alpha,1), w_i = x_i / Σ x_j.
    """
    profiles = list(PARETO_PROFILES.values())
    weights = [rng.gammavariate(alpha, 1.0) for _ in profiles]
    total = sum(weights) or 1.0
    weights = [w / total for w in weights]

    def _blend(attr: str) -> float:
        return sum(w * getattr(p, attr) for w, p in zip(weights, profiles))

    return ParetoProfile(
        name=name,
        description="Zufällige Mischung der Anker-Profile",
        w_travel      = _blend("w_travel"),
        w_revenue     = _blend("w_revenue"),
        w_fatigue     = _blend("w_fatigue"),
        w_away_streak = _blend("w_away_streak"),
        w_off_day     = _blend("w_off_day"),
        w_tv          = _blend("w_tv"),
        w_friction    = _blend("w_friction"),
    )


# ====================================================================
# Hauptfunktion: sample_pareto_frontier
# ====================================================================

def sample_pareto_frontier(
    baseline_season: Season,
    teams: List[Team],
    cfg: GeneratorConfig,
    master_seed: int = 42,
    sa_iterations: int = 3000,
    sa_start_temperature: float = 3_000_000.0,
    sa_end_temperature: float = 100.0,
    sa_shift_max_days: int = 7,
    n_interior_points: int = 4,
    events: Optional[List[LocalEvent]] = None,
    tv_cfg: Optional[TvSlotConfig] = None,
    revenue_model: Optional[RevenueModel] = None,
    verbose: bool = False,
    # Sprint 3 P1-5: optionaler Geo-Move + Feasibility/Holiday-Terme in der
    # Pareto-SA. Defaults aus → unverändertes (bit-identisches) Verhalten.
    sa_move_mix_geo: float = 0.0,
    sa_geo_topk: int = 2,
    sa_feas_lambda: float = 0.0,
    sa_holiday_lambda: float = 0.0,
) -> ParetoFrontier:
    """Berechnet die Pareto-Front über alle 8 Score-Dimensionen.

    Ablauf:
    1. Lädt externe Ressourcen (einmalig, shared über alle SA-Läufe).
    2. Führt SA für alle 6 benannten Profile durch (Anker-Pläne).
    3. Führt SA für `n_interior_points` zufällige Mischprofile durch.
    4. Filtert dominierte Pläne und gibt ≥7 nicht-dominierte zurück.

    Falls nach Schritten 2+3 weniger als N_MIN_NON_DOMINATED Pläne
    nicht-dominiert sind, werden weitere Random-Interior-Pläne berechnet
    bis das Minimum erreicht ist (oder max. 20 Gesamtläufe).

    Args:
        baseline_season:      Startplan für alle SA-Läufe.
        teams:                Alle 30 Teams.
        cfg:                  GeneratorConfig.
        master_seed:          Basis-Seed (Run i: seed = master_seed + i).
        sa_iterations:        SA-Iterationen pro Lauf.
        sa_start_temperature: SA-Starttemperatur.
        sa_end_temperature:   SA-Endtemperatur.
        sa_shift_max_days:    Max. Verschiebung für SHIFT-Moves.
        n_interior_points:    Anzahl zufälliger Interior-Läufe.
        events:               Lokale Events; None → aus data/local_events.json.
        tv_cfg:               TV-Config; None → aus data/tv_slots.json.
        revenue_model:        Revenue-Modell; None → aus data/revenue_model.json.
        verbose:              Fortschritts-Log auf stdout.

    Returns:
        ParetoFrontier mit ≥ N_MIN_NON_DOMINATED nicht-dominierten Punkten.
    """
    wall_start = time.time()
    rng_meta = random.Random(master_seed)

    # ── Ressourcen laden (einmalig) ───────────────────────────────────
    if events is None:
        events = load_local_events()
    if tv_cfg is None:
        tv_cfg = TvSlotConfig.load()
    if revenue_model is None:
        revenue_model = RevenueModel.load()

    # ── Profile definieren ────────────────────────────────────────────
    # M7 (Diversität, Sprint 2.11): Alle Läufe starten aus demselben
    # `baseline_season` (bewusste Performance-Entscheidung — spart die
    # CP-SAT-/HAP-Wiederholung pro Profil). Diversität entsteht hier dennoch aus
    # (a) je Profil unterschiedlichen Energie-Landschaften (jede Dimension anders
    # gewichtet) und (b) je Lauf unterschiedlichem SA-Seed (master_seed+run_idx),
    # der die Trajektorie ab Iteration 1 bei hoher Start-Temperatur divergieren
    # lässt. Eine echte NSGA-II-artige Start-Diversifikation (separate CP-SAT-
    # Seeds pro Profil) ist als Folgeoption dokumentiert; sie tauscht Geschwindig-
    # keit gegen Diversität und wird hier bewusst nicht aktiviert.
    anchor_profiles: List[Tuple[str, ParetoProfile]] = [
        (f"anchor_{name}", prof)
        for name, prof in PARETO_PROFILES.items()
    ]
    interior_profiles: List[Tuple[str, ParetoProfile]] = [
        (f"interior_{k}", _random_profile(rng_meta, name=f"interior_{k}"))
        for k in range(n_interior_points)
    ]
    all_profiles = anchor_profiles + interior_profiles

    all_evaluated: List[ParetoPoint] = []
    anchor_labels: List[str] = [label for label, _ in anchor_profiles]
    run_idx = 0

    # ── SA für alle Profile ───────────────────────────────────────────
    for label, profile in all_profiles:
        run_seed = master_seed + run_idx
        if verbose:
            logger.info(f"  [{run_idx+1}/{len(all_profiles)}] {label} (seed={run_seed})...")

        t0 = time.time()
        opt_season, bundle, log = optimize_pareto(
            season=baseline_season,
            teams=teams,
            cfg=cfg,
            profile=profile,
            iterations=sa_iterations,
            start_temperature=sa_start_temperature,
            end_temperature=sa_end_temperature,
            shift_max_days=sa_shift_max_days,
            seed=run_seed,
            events=events,
            tv_cfg=tv_cfg,
            revenue_model=revenue_model,
            move_mix_geo=sa_move_mix_geo,
            geo_topk=sa_geo_topk,
            feas_lambda=sa_feas_lambda,
            holiday_lambda=sa_holiday_lambda,
        )
        elapsed = time.time() - t0

        if verbose:
            logger.info(f"    → km={bundle.travel_km/1e6:.2f}M, "
                  f"rev=${bundle.revenue_usd/1e9:.2f}B, "
                  f"tv={bundle.tv_slot_score:.0f}, "
                  f"fric={bundle.event_friction:.0f}, "
                  f"cv={bundle.constraint_violations} ({elapsed:.1f}s)")

        all_evaluated.append(ParetoPoint(
            bundle=bundle,
            season=opt_season,
            label=label,
            profile_used=profile.name,
            seed_used=run_seed,
        ))
        run_idx += 1

    # ── Dominanz-Filter (erster Pass) ────────────────────────────────
    non_dominated = filter_dominated(all_evaluated)

    if verbose:
        logger.info(f"  Nach {len(all_evaluated)} Läufen: {len(non_dominated)} nicht-dominiert")

    # ── Auffüllen falls zu wenige nicht-dominierte Punkte ────────────
    max_extra = 14  # Sicherheitsnetz gegen Endlosschleife
    extra = 0
    while len(non_dominated) < N_MIN_NON_DOMINATED and extra < max_extra:
        label = f"extra_{extra}"
        run_seed = master_seed + run_idx
        extra_profile = _random_profile(rng_meta, name=label)
        if verbose:
            logger.info(f"  [extra {extra+1}] Zusätzlicher Lauf (seed={run_seed})...")
        opt_season, bundle, log = optimize_pareto(
            season=baseline_season,
            teams=teams,
            cfg=cfg,
            profile=extra_profile,
            iterations=sa_iterations,
            start_temperature=sa_start_temperature,
            end_temperature=sa_end_temperature,
            shift_max_days=sa_shift_max_days,
            seed=run_seed,
            events=events,
            tv_cfg=tv_cfg,
            revenue_model=revenue_model,
            move_mix_geo=sa_move_mix_geo,
            geo_topk=sa_geo_topk,
            feas_lambda=sa_feas_lambda,
            holiday_lambda=sa_holiday_lambda,
        )
        all_evaluated.append(ParetoPoint(
            bundle=bundle,
            season=opt_season,
            label=label,
            profile_used=extra_profile.name,
            seed_used=run_seed,
        ))
        non_dominated = filter_dominated(all_evaluated)
        run_idx += 1
        extra += 1

    # ── M6: Leere Frontier abfangen (Diagnose + Least-Bad-Fallback) ──────────
    degraded = False
    diagnostic = ""
    if not non_dominated:
        if all_evaluated:
            # Least-Bad: minimale Constraint-Verletzungen, dann kürzeste Reise.
            least_bad = min(
                all_evaluated,
                key=lambda p: (p.bundle.constraint_violations, p.bundle.travel_km),
            )
            non_dominated = [least_bad]
            degraded = True
            diagnostic = (
                f"Keine constraint-freie, nicht-dominierte Lösung in {run_idx} "
                f"SA-Läufen gefunden. Least-Bad-Plan als Fallback "
                f"(constraint_violations={least_bad.bundle.constraint_violations}, "
                f"Profil={least_bad.profile_used}). Empfehlung: violations_penalty "
                f"erhöhen, sa_iterations erhöhen oder Eingabe-Feasibilität prüfen."
            )
        else:
            degraded = True
            diagnostic = "Keine Pläne evaluiert — Frontier ist leer."
        if verbose:
            logger.info(f"  WARNUNG (M6): {diagnostic}")

    # ---- Review-Fix Runde 2 (Punkt 0): Publish-Gate je Frontier-Punkt ----
    # Jeder zurueckgegebene Plan wird gegen das projekteigene Compliance-Tooling
    # gemessen (Baseline = baseline_season; gleiche Semantik wie backtest/main/
    # whatif: keine Kategorie ueber Baseline). Die Pareto-SA selbst ist (noch)
    # nicht regel-gewahr — nicht publizierbare Punkte werden MARKIERT, nicht
    # verworfen (Explorations-Pfad). Reine Messung, kein RNG.
    try:
        from .publish_gate import publishable_report
        for p in non_dominated:
            g = publishable_report(p.season, baseline=baseline_season)
            p.publishable = g.is_publishable
            p.publish_gate_summary = g.summary()
            if verbose and not g.is_publishable:
                logger.info(f"  Publish-Gate [{p.label}]: {g.summary()}")
    except Exception as exc:  # pragma: no cover — Gate darf Pareto nie crashen
        logger.warning(f"Publish-Gate-Messung fehlgeschlagen: {exc}")

    wall_time = time.time() - wall_start

    if verbose:
        logger.info(f"  Pareto-Front: {len(non_dominated)} nicht-dominierte Pläne "
              f"in {wall_time:.1f}s ({run_idx} SA-Läufe total)")

    return ParetoFrontier(
        points=non_dominated,
        all_evaluated=all_evaluated,
        anchor_labels=anchor_labels,
        total_wall_time_s=wall_time,
        n_profiles_run=run_idx,
        master_seed=master_seed,
        degraded=degraded,
        diagnostic=diagnostic,
    )
