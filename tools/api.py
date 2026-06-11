"""REST-API-Skelett fuer den MLB Logistics Optimizer (Sprint 2.12.6).

FastAPI-Service, der die Kern-Pipeline (CP-SAT + SA), den Pareto-Explorer und
die What-if-Engine ueber HTTP verfuegbar macht — als Integrationspunkt fuer die
MLB-IT.

    pip install fastapi "uvicorn[standard]"
    uvicorn tools.api:app --reload          # Dev-Server auf http://127.0.0.1:8000
    # Interaktive Doku: http://127.0.0.1:8000/docs  (OpenAPI/Swagger)

Bewusst ein **Skelett**: die Endpoints sind vollstaendig verdrahtet und liefern
echte Ergebnisse, aber Produktionsthemen (Auth, Rate-Limiting, asynchrone
Job-Queue fuer die langen Solver-Laeufe, Persistenz der Plaene) sind als TODO
markiert und nicht implementiert. Die Schedule-Generierung dauert ~3-20 s; fuer
die Produktion gehoeren solche Laeufe in eine Background-Queue (z. B. Celery/RQ)
mit Job-IDs statt synchroner Requests.
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Dict, List, Optional

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover - Abhaengigkeit optional
    raise SystemExit(
        "FastAPI/Pydantic fehlen. Installiere mit:\n"
        '    pip install fastapi "uvicorn[standard]"'
    ) from exc

from src.data_loader import load_teams
from src.datasources import LocalFileAdapter
from src.generator import GeneratorConfig, GeneratorResult, generate
from src.matchup_extractor import extract_matchup_quotas
from src.player_fatigue import (
    all_teams_pass_fatigue_constraints,
    max_consecutive_away_days,
    max_games_without_off_day,
)
from src.season import Season

# Saison-Defaults (analog src/main.py)
DEFAULT_SEASON_START = date(2026, 3, 26)
DEFAULT_SEASON_END = date(2026, 9, 27)
DEFAULT_ALL_STAR_BREAK = (date(2026, 7, 13), date(2026, 7, 16))

app = FastAPI(
    title="MLB Logistics Optimizer API",
    version="2.12.0",
    description="Schedule-Generierung, Pareto-Exploration und What-if-Analyse.",
)

# Dev-CORS: erlaubt dem lokal geoeffneten Dashboard (dashboard/phase_tuner.html,
# file://) den Aufruf von /tune/evaluate. Fuer die Produktion auf konkrete
# Origins einschraenken (TODO unten).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ====================================================================
# Ressourcen-Loading (gecached — Stammdaten aendern sich pro Prozess nicht)
# ====================================================================

@lru_cache(maxsize=1)
def _teams_cached():
    return load_teams()


@lru_cache(maxsize=4)
def _quotas_for_source(source_season: int):
    """Matchup-Quoten aus einer realen Vorjahres-Saison (via LocalFileAdapter)."""
    adapter = LocalFileAdapter(base_dir="data")
    return extract_matchup_quotas(adapter.fetch_season_schedule(source_season))


def _build_cfg(req: "GenerateRequest") -> GeneratorConfig:
    return GeneratorConfig(
        season=req.season,
        season_start=DEFAULT_SEASON_START,
        season_end=DEFAULT_SEASON_END,
        all_star_break=DEFAULT_ALL_STAR_BREAK,
        max_solver_time_seconds=req.solver_time_seconds,
        num_search_workers=1,                 # deterministisch (AC-2.1.11)
        random_seed=req.seed,
        enable_lns_ac218_repair=req.lns_ac218_repair,
    )


# ====================================================================
# KPI-Extraktion
# ====================================================================

def _schedule_kpis(season: Season, team_ids: List[str]) -> "ScheduleKPIs":
    ok, violations = all_teams_pass_fatigue_constraints(season, team_ids)
    worst_away = max((max_consecutive_away_days(season, t) for t in team_ids), default=0)
    worst_off = max((max_games_without_off_day(season, t) for t in team_ids), default=0)
    return ScheduleKPIs(
        num_games=len(season.games),
        worst_days_away_from_home=worst_away,
        worst_games_without_off_day=worst_off,
        fatigue_constraints_ok=ok,
        constraint_violations=violations,
    )


# ====================================================================
# Pydantic-Modelle
# ====================================================================

class GenerateRequest(BaseModel):
    season: int = Field(2026, description="Zu generierende Saison.")
    source_season: int = Field(2024, description="Vorjahr fuer die Matchup-Quoten.")
    seed: int = Field(42, description="Random-Seed (bit-identische Reproduktion).")
    solver_time_seconds: float = Field(60.0, ge=1.0, le=1800.0)
    lns_ac218_repair: bool = Field(
        False, description="Optionaler gefensterter LNS-Repair fuer AC-2.1.8 (Q10)."
    )
    include_schedule: bool = Field(
        False, description="Vollstaendige Spielliste in die Antwort aufnehmen."
    )


class ScheduleKPIs(BaseModel):
    num_games: int
    worst_days_away_from_home: int
    worst_games_without_off_day: int
    fatigue_constraints_ok: bool
    constraint_violations: List[str]


class GameOut(BaseModel):
    date: str
    home: str
    away: str


class GenerateResponse(BaseModel):
    status: str
    season: int
    cp_sat_seconds: float
    travel_optimizer_seconds: float
    total_seconds: float
    initial_km: Optional[float]
    final_km: Optional[float]
    km_saved_pct: Optional[float]
    kpis: ScheduleKPIs
    # Review-Fix Runde 2 (Punkt 0): Publish-Gate-Ergebnis ist Teil JEDER
    # Plan-Antwort — ein Plan ohne bestandenes Gate darf nie unmarkiert
    # weitergereicht werden (docs/REVIEW_2026-06-10_INDEPENDENT_AI.md).
    publishable: bool = False
    publish_gate: str = ""
    schedule: Optional[List[GameOut]] = None


class ParetoRequest(GenerateRequest):
    sa_iterations: int = Field(3000, ge=100, le=1_000_000)
    n_interior_points: int = Field(4, ge=0, le=20)


class ParetoBundleOut(BaseModel):
    travel_km: float
    revenue_usd: float
    fatigue_score: float
    max_away_streak: int
    off_day_variance: float
    tv_slot_score: float
    event_friction: float
    constraint_violations: int
    # Review-Fix Runde 2 (Punkt 0): Gate-Ergebnis je Frontier-Punkt.
    publishable: Optional[bool] = None
    publish_gate: str = ""


class ParetoResponse(BaseModel):
    num_plans: int
    plans: List[ParetoBundleOut]


class BlackoutRequest(GenerateRequest):
    team: str = Field(..., description="Team-ID, dessen Heimspiele geblockt werden.")
    blackout_dates: List[str] = Field(..., description="Gesperrte Tage (ISO YYYY-MM-DD).")
    reason: str = Field("", description="Klartext-Grund (z. B. Konzert).")


class DimensionDeltaOut(BaseModel):
    dimension: str
    before: float
    after: float
    delta: float


class WhatIfResponse(BaseModel):
    feasible: bool
    scenario: str
    deltas: List[DimensionDeltaOut]
    warnings: List[str]


# ====================================================================
# Endpoints
# ====================================================================

@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "mlb-logistics-optimizer", "version": "2.12.0"}


@app.post("/schedule/generate", response_model=GenerateResponse)
def generate_schedule(req: GenerateRequest) -> GenerateResponse:
    """Generiert einen vollstaendigen Saisonplan (CP-SAT + SA)."""
    teams = _teams_cached()
    quotas = _quotas_for_source(req.source_season)
    result: GeneratorResult = generate(quotas, _build_cfg(req))
    if result.season is None:
        raise HTTPException(status_code=422, detail=f"Generierung {result.status}")

    km_saved = None
    if result.initial_km and result.final_km and result.initial_km > 0:
        km_saved = round(100.0 * (result.initial_km - result.final_km) / result.initial_km, 2)

    schedule = None
    if req.include_schedule:
        schedule = [
            GameOut(date=g.date.isoformat(), home=g.home, away=g.away)
            for g in sorted(result.season.games, key=lambda g: (g.date, g.game_pk))
        ]

    # Review-Fix Runde 2 (Punkt 0): Publish-Gate (strikt, from-scratch) — wie
    # tools/backtest.generate_our_plan. Messung + Markierung in der Antwort.
    from src.data_loader import teams_by_id as _tbi
    from src.publish_gate import publishable_report
    gate = publishable_report(result.season, _tbi(teams))

    return GenerateResponse(
        status=result.status,
        season=req.season,
        cp_sat_seconds=round(result.cp_sat_seconds, 3),
        travel_optimizer_seconds=round(result.travel_optimizer_seconds, 3),
        total_seconds=round(result.solve_time_seconds, 3),
        initial_km=result.initial_km,
        final_km=result.final_km,
        km_saved_pct=km_saved,
        kpis=_schedule_kpis(result.season, [t.id for t in teams]),
        publishable=gate.is_publishable,
        publish_gate=gate.summary(),
        schedule=schedule,
    )


@app.post("/schedule/pareto", response_model=ParetoResponse)
def pareto_frontier(req: ParetoRequest) -> ParetoResponse:
    """Erzeugt eine Pareto-Front nicht-dominierter Plaene (8 Dimensionen)."""
    from src.pareto import sample_pareto_frontier

    teams = _teams_cached()
    cfg = _build_cfg(req)
    baseline = generate(_quotas_for_source(req.source_season), cfg)
    if baseline.season is None:
        raise HTTPException(status_code=422, detail=f"Baseline {baseline.status}")

    frontier = sample_pareto_frontier(
        baseline_season=baseline.season,
        teams=teams,
        cfg=cfg,
        master_seed=req.seed,
        sa_iterations=req.sa_iterations,
        n_interior_points=req.n_interior_points,
        publishable_only=True,   # P1-5: API liefert nur publizierbare Punkte
    )
    plans = [
        ParetoBundleOut(
            travel_km=p.bundle.travel_km,
            revenue_usd=p.bundle.revenue_usd,
            fatigue_score=p.bundle.fatigue_score,
            max_away_streak=p.bundle.max_away_streak,
            off_day_variance=p.bundle.off_day_variance,
            tv_slot_score=p.bundle.tv_slot_score,
            event_friction=p.bundle.event_friction,
            constraint_violations=p.bundle.constraint_violations,
            # Punkt-Gating kommt aus sample_pareto_frontier (Punkt 0).
            publishable=p.publishable,
            publish_gate=p.publish_gate_summary,
        )
        for p in frontier.points
    ]
    return ParetoResponse(num_plans=len(plans), plans=plans)


@app.post("/whatif/blackout", response_model=WhatIfResponse)
def whatif_blackout_endpoint(req: BlackoutRequest) -> WhatIfResponse:
    """Was kostet ein Venue-Blackout (z. B. Konzert) an bestimmten Tagen?"""
    from src.whatif import whatif_blackout

    teams = _teams_cached()
    cfg = _build_cfg(req)
    baseline = generate(_quotas_for_source(req.source_season), cfg)
    if baseline.season is None:
        raise HTTPException(status_code=422, detail=f"Baseline {baseline.status}")

    try:
        dates = [date.fromisoformat(d) for d in req.blackout_dates]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Ungueltiges Datum: {exc}")

    result = whatif_blackout(
        season=baseline.season,
        teams=teams,
        cfg=cfg,
        team=req.team,
        blackout_dates=dates,
        is_home_blackout=True,
        reason=req.reason,
        scenario_name=f"blackout_{req.team}",
    )
    return WhatIfResponse(
        feasible=getattr(result, "feasible", True),
        scenario=f"blackout_{req.team}",
        deltas=[
            DimensionDeltaOut(
                dimension=d.label,
                before=d.original,
                after=d.modified,
                delta=d.delta,
            )
            for d in result.deltas
        ],
        warnings=list(result.warnings),
    )


class TuneRequest(BaseModel):
    profile_weights: Dict[str, float] = Field(
        ..., description="Gewichte aus dem Tuner-Dashboard (w_travel, w_tv, ...).")
    phase_plan: Optional[dict] = Field(
        None, description='Phasenplan {"phases": [...]} aus dem Dashboard.')
    season: int = Field(2024, description="Saison, deren realer Plan als Warm-Start dient.")
    seed: int = Field(42)
    pareto_iterations: int = Field(80_000, ge=1000, le=500_000)


@app.post("/tune/evaluate")
def tune_evaluate(req: TuneRequest) -> dict:
    """Rechnet eine Tuner-Konfiguration (Profil + Phasen) tatsaechlich durch und
    liefert echte Kennzahlen (global vs. realer Plan + pro Fenster). Schliesst die
    Feedback-Schleife des Regler-Dashboards. Laufzeit ~15-40 s (synchron;
    Produktion: Background-Queue, siehe TODO)."""
    from tools.tuning import evaluate_tuning
    try:
        return evaluate_tuning(
            profile_weights=req.profile_weights,
            phase_plan_dict=req.phase_plan,
            season_year=req.season,
            seed=req.seed,
            pareto_iterations=req.pareto_iterations,
        )
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=422, detail=str(exc))


# TODO (Produktion, nicht im Skelett):
#  - Auth (API-Key / OAuth) + Rate-Limiting.
#  - Asynchrone Job-Queue fuer generate/pareto (Job-ID + Polling statt sync).
#  - Persistenz/Caching der erzeugten Plaene (DB statt In-Memory).
#  - Weitere What-if-Endpoints (force-series, compare) analog zu /whatif/blackout.
