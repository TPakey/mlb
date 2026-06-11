"""Disruption-Orchestrator (Sprint 2.2 Hauptmodul).

Empfaengt einen bestehenden Plan und eine Disruption, dispatcht zu den drei
Strategien (A/B/C), baut pro Alternative ein ScoreBundle und liefert einen
sortierten TradeoffReport.

Wertversprechen: in <= 60 s drei substantiell verschiedene, valide Antworten
auf eine Schedule-Disruption — inklusive Tradeoff-Bewertung, die ein MLB-Ops-Team
versteht.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Union

from .data_loader import Team, load_teams
from .disruption_types import (
    Alternative, GameChange, ScoreBundle, StrategyKind, TradeoffReport,
    StadiumBlackout, WeatherWindow, MassPostponement,
)
from .generator import GeneratorConfig
from .player_fatigue import compute_fatigue_report
from .repair_local import repair_local
from .repair_regenerate import repair_regenerate
from .repair_venue_swap import repair_venue_swap
from .revenue import RevenueModel, build_division_rivals, season_revenue
from .season import Season
from .travel import compute_season_travel


DisruptionInput = Union[StadiumBlackout, WeatherWindow, MassPostponement]


# ====================================================================
# Score-Bundle-Berechnung
# ====================================================================

def _build_teams_city_lookup(teams: List[Team]) -> Dict[str, str]:
    return {t.id: t.city for t in teams}


def _compute_score(
    original: Season,
    new: Season,
    changes: List[GameChange],
    unresolved: int,
    teams: List[Team],
    revenue_model: RevenueModel,
) -> ScoreBundle:
    """Berechnet das ScoreBundle (Δ-Werte original → new)."""
    rivals = build_division_rivals(teams)

    # Travel-Delta
    orig_travel = compute_season_travel(original, teams)
    new_travel = compute_season_travel(new, teams)
    travel_km_delta = new_travel.total_km - orig_travel.total_km

    # Revenue-Delta
    orig_rev = season_revenue(original, revenue_model, rivals)
    new_rev = season_revenue(new, revenue_model, rivals)
    revenue_delta = new_rev - orig_rev

    # Fatigue-Delta
    team_ids = [t.id for t in teams]
    orig_fat = compute_fatigue_report(original, team_ids)
    new_fat = compute_fatigue_report(new, team_ids)
    fatigue_delta = new_fat.league_total_fatigue - orig_fat.league_total_fatigue

    # Affected Teams: aus den changes
    affected_team_ids = set()
    orig_by_pk = {g.game_pk: g for g in original.games}
    for c in changes:
        og = orig_by_pk.get(c.original_game_pk)
        if og is None:
            continue
        affected_team_ids.add(og.home)
        affected_team_ids.add(og.away)
        if c.new_home and c.new_home != og.home:
            affected_team_ids.add(c.new_home)
        if c.new_away and c.new_away != og.away:
            affected_team_ids.add(c.new_away)
    affected_teams = len(affected_team_ids)

    # Change-Quote
    change_pct = len(changes) / max(1, len(original.games))

    # ---- Review-Fix P0-3 + Runde 2 Punkt 0 (2026-06-10): VOLLES Publish-Gate
    # auf dem REPARIERTEN Plan, nicht nur unverlegbare Spiele zaehlen.
    # Baseline-relativ: Verstoesse, die schon der Original-Plan trug
    # (as-played-Artefakte), zaehlen nicht gegen die Reparatur — aber jeder
    # NEUE Verstoss (z. B. >20-Tage-Streak nach Makeup [V(C)(12)/AC-2.1.9,
    # P0-3-Befund: 25-Tage-Streak], PT→ET ohne Off-Day, Envelope-Bruch,
    # V(C)(13)/(14)/(15)-Struktur) macht die Alternative invalide.
    from .publish_gate import publishable_report
    gate = publishable_report(new, baseline=original)
    introduced = len(gate.new_hard_failures) + len(gate.new_structural)

    return ScoreBundle(
        travel_km_delta=travel_km_delta,
        affected_teams=affected_teams,
        revenue_delta_usd=revenue_delta,
        fatigue_delta=fatigue_delta,
        change_pct=change_pct,
        hard_constraint_violations=unresolved + introduced,
    )


# ====================================================================
# Pro-Strategie-Builder
# ====================================================================

def _run_strategy_a(
    original: Season,
    disruption: DisruptionInput,
    teams: List[Team],
    revenue_model: RevenueModel,
    teams_city_lookup: Dict[str, str],
) -> Alternative:
    t0 = time.perf_counter()
    new_season, changes, unresolved = repair_local(original, disruption, teams_city_lookup)
    runtime = time.perf_counter() - t0
    score = _compute_score(original, new_season, changes, len(unresolved), teams, revenue_model)
    return Alternative(
        strategy=StrategyKind.LOCAL_REPAIR,
        label="A — Postpone-to-Next-Off-Day",
        season=new_season,
        changes=tuple(changes),
        score=score,
        runtime_seconds=runtime,
        notes=f"unresolved={len(unresolved)} Spiele" if unresolved else "",
    )


def _run_strategy_b(
    original: Season,
    disruption: DisruptionInput,
    cfg_template: GeneratorConfig,
    teams: List[Team],
    revenue_model: RevenueModel,
    teams_city_lookup: Dict[str, str],
) -> Alternative:
    t0 = time.perf_counter()
    new_season, changes, gen_result = repair_regenerate(
        original, disruption, cfg_template, teams_city_lookup
    )
    runtime = time.perf_counter() - t0
    violations = 0 if gen_result.status in ("OPTIMAL", "FEASIBLE") else 1
    score = _compute_score(original, new_season, changes, violations, teams, revenue_model)
    return Alternative(
        strategy=StrategyKind.CONSTRAINED_REGENERATE,
        label="B — Constrained Re-Generate",
        season=new_season,
        changes=tuple(changes),
        score=score,
        runtime_seconds=runtime,
        notes=f"CP-SAT status={gen_result.status}",
    )


def _run_strategy_c(
    original: Season,
    disruption: DisruptionInput,
    teams: List[Team],
    revenue_model: RevenueModel,
    teams_city_lookup: Dict[str, str],
) -> Alternative:
    t0 = time.perf_counter()
    new_season, changes, unresolved = repair_venue_swap(original, disruption, teams_city_lookup)
    runtime = time.perf_counter() - t0
    score = _compute_score(original, new_season, changes, len(unresolved), teams, revenue_model)
    return Alternative(
        strategy=StrategyKind.VENUE_SWAP,
        label="C — Venue-Swap mit Revanche",
        season=new_season,
        changes=tuple(changes),
        score=score,
        runtime_seconds=runtime,
        notes=f"unresolved={len(unresolved)} Spiele" if unresolved else "",
    )


# ====================================================================
# Haupt-API
# ====================================================================

def handle_disruption(
    original_season: Season,
    disruption: DisruptionInput,
    cfg_template: GeneratorConfig,
    teams: Optional[List[Team]] = None,
    revenue_model: Optional[RevenueModel] = None,
) -> TradeoffReport:
    """Hauptverbindung: dispatcht alle drei Strategien parallel-konzeptuell
    (aktuell seriell), baut Score-Bundles, sortiert und liefert den Report.

    Sortierung der Alternativen ist DETERMINISTISCH nach Strategy-Reihenfolge
    A < B < C, damit Output reproduzierbar ist (AC-2.2.7).
    """
    if teams is None:
        teams = load_teams(cfg_template.teams_path)
    if revenue_model is None:
        revenue_model = RevenueModel.load()

    teams_city_lookup = _build_teams_city_lookup(teams)

    t_global = time.perf_counter()
    alt_a = _run_strategy_a(original_season, disruption, teams, revenue_model, teams_city_lookup)
    alt_b = _run_strategy_b(original_season, disruption, cfg_template, teams, revenue_model, teams_city_lookup)
    alt_c = _run_strategy_c(original_season, disruption, teams, revenue_model, teams_city_lookup)
    total_runtime = time.perf_counter() - t_global

    # Disruption-Summary fuer den Report
    summary = _disruption_summary(disruption)

    return TradeoffReport(
        disruption_summary=summary,
        original_total_games=len(original_season.games),
        alternatives=(alt_a, alt_b, alt_c),    # deterministisch A < B < C
        total_runtime_seconds=total_runtime,
    )


def _disruption_summary(disruption: DisruptionInput) -> str:
    if isinstance(disruption, StadiumBlackout):
        return (
            f"Stadium-Blackout: {disruption.home_team}, "
            f"{disruption.start_date}..{disruption.end_date}"
            + (f" — {disruption.reason}" if disruption.reason else "")
        )
    if isinstance(disruption, WeatherWindow):
        return (
            f"Weather-Window: {disruption.city}, "
            f"{disruption.start_date}..{disruption.end_date}, severity={disruption.severity}"
            + (f" — {disruption.reason}" if disruption.reason else "")
        )
    if isinstance(disruption, MassPostponement):
        return (
            f"Mass-Postponement: {len(disruption.game_pks)} Spiele"
            + (f" — {disruption.reason}" if disruption.reason else "")
        )
    return "Unbekannte Disruption"
