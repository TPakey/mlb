"""Backtest — unser optimierter Plan vs. der echte MLB-Spielplan (Sprint 3, Track B).

Dieses Tool beantwortet die *Glaubwürdigkeits-Frage* der MLB League Officials:
"Ist euer Plan messbar besser als der echte Spielplan?" — und zwar ehrlich, auf
allen acht Bewertungsdimensionen (`ParetoBundle`) plus einer Pro-Team-Reise-km-
Aufschlüsselung.

Vorgehen (Charter B1–B3):
    B1  Realen MLB-Plan (data/mlb_schedule_<jahr>.json) laden und mit UNSEREM
        Scoring bewerten  ->  "MLB-Ist-Baseline".
    B2  Unseren Generator unter demselben Saisonfenster + denselben Matchup-
        Quoten laufen lassen  ->  "Optimizer-Plan".
    B3  Side-by-Side-Report (Markdown + HTML + JSON) mit Deltas + Pro-Team-
        Aufschlüsselung schreiben.

Ehrlichkeits-Gebot (Charter): Unser Plan muss NICHT auf jeder Achse besser sein.
MLB optimiert auch Dinge, die wir nicht modellieren (nationale TV-Deals, Stadion-
Verfügbarkeit, Sonderserien im Ausland). Der Report benennt das ausdrücklich.

Beispiele:
    python -m tools.backtest --season 2024
    python -m tools.backtest --season 2025 --seed 7 --solver-time 120
    python -m tools.backtest --season 2024 --baseline-only      # nur B1
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logging.basicConfig(
    level="INFO",
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("mlb.backtest")

from src.data_loader import load_teams
from src.datasources import LocalFileAdapter
from src.generator import GeneratorConfig, generate
from src.matchup_extractor import extract_matchup_quotas
from src.pareto_types import ParetoBundle, compute_pareto_bundle
from src.season import Season, detect_all_star_break
from src.travel import SeasonTravelReport, compute_season_travel
from src.sustainability import compute_co2_report
from src.fairness import compute_fairness_report

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output" / "backtest"


# ====================================================================
# Dimensions-Metadaten (Richtung + Anzeige)
# ====================================================================

# (key, Anzeige-Name, Einheit, "higher_is_better")
DIMENSIONS: Tuple[Tuple[str, str, str, bool], ...] = (
    ("travel_km",            "Reisedistanz",        "km",      False),
    ("revenue_usd",          "Erwarteter Revenue",  "USD",     True),
    ("fatigue_score",        "Fatigue-Score",       "Punkte",  False),
    ("max_away_streak",      "Max. Auswärts-Streak","Tage",    False),
    ("off_day_variance",     "Off-Day-Varianz",     "",        False),
    ("tv_slot_score",        "TV-Slot-Score",       "Punkte",  True),
    ("event_friction",       "Event-Friction",      "Punkte",  False),
    ("constraint_violations","CBA-Verletzungen",    "Anzahl",  False),
)


# ====================================================================
# Datencontainer
# ====================================================================

@dataclass
class PlanEvaluation:
    """Ein bewerteter Plan (real oder generiert)."""
    label: str
    season: Season
    bundle: ParetoBundle
    travel: SeasonTravelReport
    n_games: int
    n_doubleheaders: int
    season_start: Optional[date]
    season_end: Optional[date]
    # Generator-Diagnostik (None für den realen Plan)
    solve_seconds: Optional[float] = None
    status: Optional[str] = None
    seed: Optional[int] = None


@dataclass
class BacktestResult:
    season_year: int
    baseline: PlanEvaluation
    ours: Optional[PlanEvaluation]


# ====================================================================
# B1 — Reale Baseline
# ====================================================================

def load_real_baseline(season_year: int) -> PlanEvaluation:
    """Lädt den echten MLB-Plan und bewertet ihn mit unserem Scoring."""
    adapter = LocalFileAdapter(base_dir=str(DATA_DIR))
    season = adapter.fetch_season_schedule(season_year)
    teams = load_teams()
    logger.info("B1: realer MLB-Plan %s geladen (%d Spiele)", season_year, len(season.games))
    bundle = compute_pareto_bundle(season, teams)
    travel = compute_season_travel(season, teams)
    n_dh = sum(1 for g in season.games if g.doubleheader_seq > 0) // 2
    return PlanEvaluation(
        label=f"MLB-Ist {season_year}",
        season=season,
        bundle=bundle,
        travel=travel,
        n_games=len(season.games),
        n_doubleheaders=n_dh,
        season_start=season.season_start,
        season_end=season.season_end,
    )


# ====================================================================
# B2 — Unser generierter Plan (gleiches Fenster, gleiche Quoten)
# ====================================================================

# ASB-Erkennung liegt jetzt zentral in src/season.detect_all_star_break
# (gemeinsam genutzt mit src/main.py). Alias fuer Rueckwaertskompatibilitaet.
_detect_all_star_break = detect_all_star_break


def generate_our_plan(
    season_year: int,
    seed: int = 42,
    solver_time: float = 60.0,
    enable_lns_repair: bool = False,
) -> PlanEvaluation:
    """Generiert unseren Plan mit den Matchup-Quoten + dem Fenster der realen Saison.

    Damit ist der Vergleich fair: identische Paarungs-Quoten, identisches
    Kalenderfenster, identischer All-Star-Break.
    """
    adapter = LocalFileAdapter(base_dir=str(DATA_DIR))
    real = adapter.fetch_season_schedule(season_year)
    quotas = extract_matchup_quotas(real)
    teams = load_teams()

    asb = _detect_all_star_break(real)
    # Review-Runde 2 (Punkt 2): VENUE-AVAIL auch im from-scratch-Pfad.
    from src.event_conflicts import (load_local_events,
                                     stadium_bookings_to_blackout_days)
    events = load_local_events()
    blackouts = stadium_bookings_to_blackout_days(events, real.season_start,
                                                  real.season_end)
    cfg = GeneratorConfig(
        season=season_year,
        season_start=real.season_start,
        season_end=real.season_end,
        all_star_break=asb,
        max_solver_time_seconds=solver_time,
        num_search_workers=1,
        random_seed=seed,
        enforce_fatigue_constraints=True,
        enable_lns_ac218_repair=enable_lns_repair,
        home_blackout_days=blackouts,
        # Offizieller Vergleich: hohes Travel-Budget fuer den bestmoeglichen Plan
        # (der Default ist bewusst moderat fuer interaktive Pfade).
        travel_optimizer_iterations=6_000_000,
    )
    logger.info(
        "B2: generiere unseren Plan %s (Fenster %s..%s, ASB %s, Seed %d) ...",
        season_year, real.season_start, real.season_end,
        f"{asb[0]}..{asb[1]}" if asb else "—", seed,
    )
    t0 = time.time()
    result = generate(quotas, cfg)
    elapsed = time.time() - t0
    if result.season is None:
        raise RuntimeError(
            f"Generator lieferte keinen Plan (Status {result.status}). "
            f"Bei UNKNOWN/TIMEOUT: --solver-time erhöhen (manche Saison-Quoten, "
            f"z.B. 2025, brauchen mit enforce_fatigue_constraints deutlich mehr "
            f"CP-SAT-Zeit als 2024). Qualität vor Geschwindigkeit."
        )
    season = result.season
    # ---- Publish-Gate (Review-Fix P0-1), strikter Original-Massstab.
    # From-scratch ist explizit NUR Algorithmus-Validierung (kein Produktions-
    # pfad) → Gate-Ergebnis wird geloggt und im Label markiert statt zu werfen.
    from src.publish_gate import publishable_report
    from src.data_loader import teams_by_id as _tbi
    gate = publishable_report(season, _tbi(teams), events=events)
    logger.info("Publish-Gate (from-scratch, strikt): %s", gate.summary())
    gate_suffix = "" if gate.is_publishable else " [NICHT PUBLIZIERBAR]"
    bundle = compute_pareto_bundle(season, teams)
    travel = compute_season_travel(season, teams)
    n_dh = sum(1 for g in season.games if g.doubleheader_seq > 0) // 2
    logger.info("B2: Plan generiert in %.1fs (Status %s, %d Spiele)",
                elapsed, result.status, len(season.games))
    return PlanEvaluation(
        label=f"Optimizer {season_year}{gate_suffix}",
        season=season,
        bundle=bundle,
        travel=travel,
        n_games=len(season.games),
        n_doubleheaders=n_dh,
        season_start=season.season_start,
        season_end=season.season_end,
        solve_seconds=elapsed,
        status=result.status,
        seed=seed,
    )


# ====================================================================
# Warm-Start — den REALEN Plan als Startpunkt nehmen und optimieren
# ====================================================================

def improve_real_plan(
    season_year: int,
    seed: int = 42,
    iterations: int = 6_000_000,
    *,
    legacy_bitident: bool = False,
    allow_unpublishable: bool = False,
) -> PlanEvaluation:
    """Nimmt den echten MLB-Plan als Startpunkt und optimiert ihn mit unserem
    SA-Optimizer (Geo-Move). Realistischer Produktionsfall: fuer eine neue Saison
    startet man vom (strukturell fast identischen) Vorjahresplan und passt ihn an.

    Review-Fix P0-1 (2026-06-10): Der Produktions-Default laeuft mit AKTIVEN
    Regel-Schutztermen (production_optimizer_config: V(C)(11)-PTET, Reise-
    Envelope, V(C)(13)) und der Output wird VOR der Ausweisung gegen das
    projekteigene Compliance-Tooling gemessen (publish_gate, Baseline = realer
    Plan). Nicht publizierbarer Output wirft UnpublishableScheduleError.
    ``legacy_bitident=True`` reproduziert das alte, UNGESCHUETZTE Verhalten
    (bit-identisch zu Alt-Messungen) — Gate-Verstoesse werden dann nur laut
    geloggt und das Label markiert (kein Produktionsmodus!).
    """
    from src.generator_optimizer import (OptimizerConfig, optimize_travel,
                                         production_optimizer_config)
    from src.publish_gate import publishable_report, UnpublishableScheduleError
    from src.data_loader import teams_by_id as _tbi

    adapter = LocalFileAdapter(base_dir=str(DATA_DIR))
    real = adapter.fetch_season_schedule(season_year)
    teams = load_teams()
    asb = _detect_all_star_break(real)
    # Review-Runde 2 (Punkt 2): VENUE-AVAIL aktiv im Produktionslauf — Stadion-
    # Belegungen werden als harte Blackout-Tage an die SA gegeben UND im Gate
    # geprüft. (Hinweis Datenlage: local_events.json deckt aktuell 2026 ab;
    # für 2024/2025-Backtests binden 0 Tage — gemessen, nicht verschwiegen.)
    from src.event_conflicts import (load_local_events,
                                     stadium_bookings_to_blackout_days)
    events = load_local_events()
    blackouts = ({} if legacy_bitident else
                 stadium_bookings_to_blackout_days(events, real.season_start,
                                                   real.season_end))
    cfg = GeneratorConfig(
        season=season_year,
        season_start=real.season_start,
        season_end=real.season_end,
        all_star_break=asb,
        max_solver_time_seconds=60,
        num_search_workers=1,
        random_seed=seed,
        enforce_fatigue_constraints=True,
        travel_optimizer_iterations=iterations,
        home_blackout_days=blackouts,
    )
    if legacy_bitident:
        logger.warning(
            "⚠️ --legacy-bitident: Regel-Schutzterme AUS (Alt-Verhalten). Der "
            "Output kann harte CBA-Verstoesse enthalten (gemessen: V(C)(11) 18x "
            "auf 2024). NUR fuer Reproduktion alter Messungen.")
        oc = OptimizerConfig(
            iterations=iterations,
            shift_max_days=cfg.travel_optimizer_shift_max_days,
            move_mix_geo=0.35,
            seed=seed,
            fatigue_lambda=1_000_000.0,  # wie generate() bei enforce_fatigue_constraints
        )
    else:
        oc = production_optimizer_config(
            iterations=iterations,
            shift_max_days=cfg.travel_optimizer_shift_max_days,
            move_mix_geo=0.35,
            seed=seed,
        )
    logger.info("Warm-Start: optimiere realen Plan %s (Seed %d, %d Iter) ...",
                season_year, seed, iterations)
    t0 = time.time()
    improved, _log = optimize_travel(real, teams, cfg, oc)
    elapsed = time.time() - t0

    # ---- Publish-Gate (Review-Fix P0-1): Output MESSEN, bevor er als
    # Ergebnis ausgewiesen wird. Baseline = realer Input-Plan (as-played).
    # Runde 2 (Punkt 2): inkl. hartem VENUE-AVAIL-Check (events).
    gate = publishable_report(improved, _tbi(teams), baseline=real, events=events)
    logger.info("Publish-Gate: %s", gate.summary())
    label_suffix = ""
    if not gate.is_publishable:
        if legacy_bitident or allow_unpublishable:
            logger.error("⛔ %s — Ergebnis wird als NICHT PUBLIZIERBAR markiert.",
                         gate.summary())
            label_suffix = " [NICHT PUBLIZIERBAR]"
        else:
            raise UnpublishableScheduleError(
                f"Warm-Start {season_year}: {gate.summary()} — Abbruch. "
                f"(--allow-unpublishable um den Plan trotzdem zu inspizieren.)")
    bundle = compute_pareto_bundle(improved, teams)
    travel = compute_season_travel(improved, teams)
    n_dh = sum(1 for g in improved.games if g.doubleheader_seq > 0) // 2
    logger.info("Warm-Start fertig in %.1fs", elapsed)
    return PlanEvaluation(
        label=f"Optimizer (Warm-Start) {season_year}{label_suffix}",
        season=improved,
        bundle=bundle,
        travel=travel,
        n_games=len(improved.games),
        n_doubleheaders=n_dh,
        season_start=improved.season_start,
        season_end=improved.season_end,
        solve_seconds=elapsed,
        status="WARM_START",
        seed=seed,
    )


# ====================================================================
# B3 — Delta-Berechnung + Report
# ====================================================================

def _pct_delta(ours: float, base: float) -> Optional[float]:
    if base == 0:
        return None
    return (ours - base) / abs(base) * 100.0


def _verdict(key: str, higher_is_better: bool, ours: float, base: float) -> str:
    """'besser' / 'schlechter' / 'gleich' aus unserer Sicht (Optimizer vs. Ist)."""
    if ours == base:
        return "gleich"
    ours_better = (ours > base) if higher_is_better else (ours < base)
    return "besser" if ours_better else "schlechter"


def _fmt(key: str, value: float) -> str:
    if key == "revenue_usd":
        return f"${value/1e6:,.1f} Mio"
    if key == "travel_km":
        return f"{value:,.0f} km"
    if key in ("max_away_streak", "constraint_violations"):
        return f"{int(value)}"
    if key == "off_day_variance":
        return f"{value:.4f}"
    return f"{value:,.1f}"


def compute_dimension_rows(result: BacktestResult) -> List[Dict[str, object]]:
    """Erzeugt strukturierte Vergleichszeilen pro Dimension."""
    rows: List[Dict[str, object]] = []
    base = result.baseline.bundle
    ours = result.ours.bundle if result.ours else None
    for key, name, unit, higher in DIMENSIONS:
        bv = float(getattr(base, key))
        row: Dict[str, object] = {
            "key": key, "name": name, "unit": unit, "higher_is_better": higher,
            "baseline": bv, "baseline_fmt": _fmt(key, bv),
        }
        if ours is not None:
            ov = float(getattr(ours, key))
            row.update({
                "ours": ov, "ours_fmt": _fmt(key, ov),
                "delta": ov - bv,
                "pct": _pct_delta(ov, bv),
                "verdict": _verdict(key, higher, ov, bv),
            })
        rows.append(row)
    return rows


def per_team_travel_rows(result: BacktestResult) -> List[Dict[str, object]]:
    """Pro-Team-Reise-km: Ist vs. Optimizer, sortiert nach Ist-km (absteigend)."""
    base = result.baseline.travel.by_team
    ours = result.ours.travel.by_team if result.ours else {}
    rows: List[Dict[str, object]] = []
    for tid in sorted(base.keys(), key=lambda t: -base[t].total_km):
        b_km = base[tid].total_km
        row: Dict[str, object] = {"team": tid, "baseline_km": b_km}
        if tid in ours:
            o_km = ours[tid].total_km
            row.update({"ours_km": o_km, "delta_km": o_km - b_km,
                        "pct": _pct_delta(o_km, b_km)})
        rows.append(row)
    return rows


# ---- Markdown ----

def render_markdown(result: BacktestResult) -> str:
    b = result.baseline
    o = result.ours
    L: List[str] = []
    L.append(f"# Backtest — Optimizer vs. echter MLB-Plan ({result.season_year})")
    L.append("")
    L.append(f"**Erstellt:** {date.today().isoformat()} · **Saison:** {result.season_year}")
    L.append("")
    L.append("> **Ehrlichkeits-Gebot.** Dieser Report bewertet beide Pläne mit *unserem* "
             "8-dimensionalen Scoring. Der reale MLB-Plan optimiert auch Faktoren, die wir "
             "nicht modellieren (nationale TV-Deals, Stadion-Verfügbarkeit, Auslandsserien, "
             "Doubleheader-Makeups). Wo wir schlechter sind, steht das hier ungeschönt.")
    L.append("")
    # Kontext-Tabelle
    L.append("## Vergleichskontext")
    L.append("")
    L.append("| | MLB-Ist | Optimizer |")
    L.append("|---|---|---|")
    L.append(f"| Spiele | {b.n_games} | {o.n_games if o else '—'} |")
    L.append(f"| Doubleheader | {b.n_doubleheaders} | {o.n_doubleheaders if o else '—'} |")
    L.append(f"| Fenster | {b.season_start}..{b.season_end} | "
             f"{(str(o.season_start)+'..'+str(o.season_end)) if o else '—'} |")
    if o:
        L.append(f"| Generierung | — | {o.status}, {o.solve_seconds:.1f}s, Seed {o.seed} |")
    L.append("")
    L.append("> Hinweis: Der reale Plan enthält Doubleheader (oft Wetter-Makeups) und eine "
             "ungleiche Heim/Auswärts-Verteilung; unser Generator erzeugt ein sauberes "
             "162-Spiele-Schema. Kleinere Spielzahl-Differenzen sind dadurch erklärt und in "
             "den Deltas berücksichtigt (Track B4 eicht das Reisemodell weiter).")
    L.append("")
    # Dimensions-Tabelle
    L.append("## Bewertung über alle 8 Dimensionen")
    L.append("")
    if o:
        L.append("| Dimension | MLB-Ist | Optimizer | Δ | Δ % | Urteil |")
        L.append("|---|---:|---:|---:|---:|:--:|")
        for r in compute_dimension_rows(result):
            pct = r.get("pct")
            pct_s = f"{pct:+.1f}%" if isinstance(pct, float) else "—"
            arrow = {"besser": "✅", "schlechter": "❌", "gleich": "➖"}[r["verdict"]]
            L.append(f"| {r['name']} | {r['baseline_fmt']} | {r['ours_fmt']} | "
                     f"{_fmt(r['key'], r['delta']) if r['key'] not in ('revenue_usd',) else ('$'+format(r['delta']/1e6, ',.1f')+' Mio')} | "
                     f"{pct_s} | {arrow} {r['verdict']} |")
    else:
        L.append("| Dimension | MLB-Ist |")
        L.append("|---|---:|")
        for r in compute_dimension_rows(result):
            L.append(f"| {r['name']} | {r['baseline_fmt']} |")
    L.append("")
    # Lesehilfe / Zusammenfassung
    if o:
        rows = compute_dimension_rows(result)
        better = [r["name"] for r in rows if r.get("verdict") == "besser"]
        worse = [r["name"] for r in rows if r.get("verdict") == "schlechter"]
        L.append("### Zusammenfassung")
        L.append("")
        L.append(f"- **Besser als der reale Plan:** {', '.join(better) if better else '—'}")
        L.append(f"- **Schlechter:** {', '.join(worse) if worse else '—'}")
        L.append("")
    # Pro-Team-km
    L.append("## Pro-Team-Reisedistanz")
    L.append("")
    if o:
        L.append("| Team | MLB-Ist (km) | Optimizer (km) | Δ km | Δ % |")
        L.append("|---|---:|---:|---:|---:|")
        for r in per_team_travel_rows(result):
            pct = r.get("pct")
            pct_s = f"{pct:+.1f}%" if isinstance(pct, float) else "—"
            ours_km = r.get("ours_km")
            L.append(f"| {r['team']} | {r['baseline_km']:,.0f} | "
                     f"{ours_km:,.0f} | {r['delta_km']:+,.0f} | {pct_s} |"
                     if ours_km is not None else
                     f"| {r['team']} | {r['baseline_km']:,.0f} | — | — | — |")
    else:
        L.append("| Team | MLB-Ist (km) |")
        L.append("|---|---:|")
        for r in per_team_travel_rows(result):
            L.append(f"| {r['team']} | {r['baseline_km']:,.0f} |")
    L.append("")
    # CO₂ + Fairness (Charter C3)
    L.append("## Nachhaltigkeit & Fairness")
    L.append("")
    co2_b = compute_co2_report(b.travel)
    fair_b = compute_fairness_report(b.travel)
    if o:
        co2_o = compute_co2_report(o.travel)
        fair_o = compute_fairness_report(o.travel)
        d_co2 = co2_o.total_tonnes - co2_b.total_tonnes
        pct_co2 = 100.0 * d_co2 / co2_b.total_tonnes if co2_b.total_tonnes else 0.0
        d_gini = fair_o.gini - fair_b.gini
        L.append("| Kennzahl | MLB-Ist | Optimizer | Δ |")
        L.append("|---|---:|---:|---:|")
        L.append(f"| CO₂ gesamt (t) | {co2_b.total_tonnes:,.0f} | {co2_o.total_tonnes:,.0f} | "
                 f"{d_co2:+,.0f} ({pct_co2:+.1f}%) |")
        L.append(f"| CO₂ Ø/Team (t) | {co2_b.avg_tonnes_per_team:,.0f} | "
                 f"{co2_o.avg_tonnes_per_team:,.0f} | — |")
        L.append(f"| Gini (Reiselast) | {fair_b.gini:.3f} | {fair_o.gini:.3f} | {d_gini:+.3f} |")
        L.append(f"| Disparität (max/min) | {fair_b.disparity_ratio:.2f}× | "
                 f"{fair_o.disparity_ratio:.2f}× | — |")
        L.append(f"| Reiseintensivstes / -ärmstes Team | {fair_b.max_team}/{fair_b.min_team} | "
                 f"{fair_o.max_team}/{fair_o.min_team} | — |")
    else:
        L.append("| Kennzahl | MLB-Ist |")
        L.append("|---|---:|")
        L.append(f"| CO₂ gesamt (t) | {co2_b.total_tonnes:,.0f} |")
        L.append(f"| Gini (Reiselast) | {fair_b.gini:.3f} |")
        L.append(f"| Disparität (max/min) | {fair_b.disparity_ratio:.2f}× |")
    L.append("")
    L.append(f"> CO₂-Faktor: {co2_b.kg_per_km_factor:.2f} kg/km (ICAO Jet-A × 737-800-Burn, "
             "Beleg: docs/SUSTAINABILITY_RESEARCH.md). Gini 0 = perfekt gleiche Reiselast, "
             "1 = maximal ungleich. Niedriger ist fairer.")
    L.append("")
    L.append("---")
    L.append("")
    L.append("*Reproduzierbar: `python -m tools.backtest --season "
             f"{result.season_year}`. Deterministisch (1 Worker, fixer Seed).*")
    return "\n".join(L)


def _sustainability_json(ev) -> dict:
    """CO₂/Fairness-Block für den JSON-Report (Charter C3)."""
    co2 = compute_co2_report(ev.travel)
    fair = compute_fairness_report(ev.travel)
    return {
        "co2_total_tonnes": round(co2.total_tonnes, 1),
        "co2_avg_per_team_tonnes": round(co2.avg_tonnes_per_team, 1),
        "co2_kg_per_km_factor": co2.kg_per_km_factor,
        "fairness_gini": round(fair.gini, 4),
        "fairness_disparity_ratio": round(fair.disparity_ratio, 3),
        "fairness_max_team": fair.max_team,
        "fairness_min_team": fair.min_team,
    }


# ---- HTML ----

def render_html(result: BacktestResult) -> str:
    md_rows = compute_dimension_rows(result)
    team_rows = per_team_travel_rows(result)
    o = result.ours
    badge = {"besser": ("#157f3b", "✅ besser"),
             "schlechter": ("#b3261e", "❌ schlechter"),
             "gleich": ("#5f6368", "➖ gleich")}

    def dim_tr(r):
        if not o:
            return f"<tr><td>{r['name']}</td><td class='num'>{r['baseline_fmt']}</td></tr>"
        pct = r.get("pct")
        pct_s = f"{pct:+.1f}%" if isinstance(pct, float) else "—"
        col, txt = badge[r["verdict"]]
        return (f"<tr><td>{r['name']}</td>"
                f"<td class='num'>{r['baseline_fmt']}</td>"
                f"<td class='num'>{r['ours_fmt']}</td>"
                f"<td class='num'>{pct_s}</td>"
                f"<td style='color:{col};font-weight:600'>{txt}</td></tr>")

    def team_tr(r):
        ours_km = r.get("ours_km")
        if ours_km is None:
            return f"<tr><td>{r['team']}</td><td class='num'>{r['baseline_km']:,.0f}</td></tr>"
        pct = r.get("pct")
        pct_s = f"{pct:+.1f}%" if isinstance(pct, float) else "—"
        col = "#157f3b" if r["delta_km"] < 0 else ("#b3261e" if r["delta_km"] > 0 else "#5f6368")
        return (f"<tr><td>{r['team']}</td>"
                f"<td class='num'>{r['baseline_km']:,.0f}</td>"
                f"<td class='num'>{ours_km:,.0f}</td>"
                f"<td class='num' style='color:{col}'>{r['delta_km']:+,.0f}</td>"
                f"<td class='num'>{pct_s}</td></tr>")

    dim_head = ("<tr><th>Dimension</th><th>MLB-Ist</th><th>Optimizer</th>"
                "<th>Δ %</th><th>Urteil</th></tr>" if o
                else "<tr><th>Dimension</th><th>MLB-Ist</th></tr>")
    team_head = ("<tr><th>Team</th><th>MLB-Ist (km)</th><th>Optimizer (km)</th>"
                 "<th>Δ km</th><th>Δ %</th></tr>" if o
                 else "<tr><th>Team</th><th>MLB-Ist (km)</th></tr>")
    b = result.baseline
    ctx = (f"Spiele {b.n_games} vs. {o.n_games} · "
           f"Generierung {o.status}, {o.solve_seconds:.1f}s, Seed {o.seed}"
           if o else f"Spiele {b.n_games} · nur Baseline")

    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Backtest {result.season_year} — Optimizer vs. MLB-Ist</title>
<style>
  :root {{ --navy:#0c2340; --red:#bf0d3e; }}
  body {{ font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
         margin:0; color:#1a1a1a; background:#f6f7f9; }}
  header {{ background:var(--navy); color:#fff; padding:24px 32px; }}
  header h1 {{ margin:0 0 4px; font-size:22px; }}
  header .ctx {{ opacity:.85; font-size:13px; }}
  main {{ max-width:980px; margin:0 auto; padding:24px 32px 64px; }}
  .note {{ background:#fff8e1; border-left:4px solid #f5b400; padding:12px 16px;
          border-radius:6px; font-size:14px; margin:18px 0; }}
  h2 {{ font-size:17px; margin:28px 0 10px; color:var(--navy); }}
  table {{ width:100%; border-collapse:collapse; background:#fff; border-radius:8px;
          overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,.08); font-size:14px; }}
  th,td {{ padding:9px 12px; text-align:left; border-bottom:1px solid #eef0f2; }}
  th {{ background:#f0f2f5; font-weight:600; }}
  td.num,th.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  td:nth-child(n+2),th:nth-child(n+2) {{ text-align:right; }}
  td:first-child,th:first-child {{ text-align:left; }}
  footer {{ color:#5f6368; font-size:12px; margin-top:24px; }}
</style></head>
<body>
<header>
  <h1>Backtest {result.season_year} — Optimizer vs. echter MLB-Plan</h1>
  <div class="ctx">{ctx}</div>
</header>
<main>
  <div class="note"><b>Ehrlichkeits-Gebot.</b> Beide Pläne mit <i>unserem</i> Scoring bewertet.
  Der reale MLB-Plan optimiert auch Ungemodelltes (nationale TV-Deals, Stadion-Verfügbarkeit,
  Auslandsserien). Wo wir schlechter sind, steht es hier ungeschönt.</div>
  <h2>Bewertung über alle 8 Dimensionen</h2>
  <table><thead>{dim_head}</thead><tbody>
  {''.join(dim_tr(r) for r in md_rows)}
  </tbody></table>
  <h2>Pro-Team-Reisedistanz</h2>
  <table><thead>{team_head}</thead><tbody>
  {''.join(team_tr(r) for r in team_rows)}
  </tbody></table>
  <footer>Reproduzierbar: <code>python -m tools.backtest --season {result.season_year}</code>
  · deterministisch (1 Worker, fixer Seed) · erstellt {date.today().isoformat()}</footer>
</main></body></html>"""


# ---- JSON ----

def render_json(result: BacktestResult) -> dict:
    out = {
        "season_year": result.season_year,
        "generated": date.today().isoformat(),
        "baseline": {
            "label": result.baseline.label,
            "n_games": result.baseline.n_games,
            "n_doubleheaders": result.baseline.n_doubleheaders,
            "bundle": result.baseline.bundle.to_dict(),
        },
        "dimensions": compute_dimension_rows(result),
        "per_team_travel": per_team_travel_rows(result),
        "sustainability": _sustainability_json(result.baseline),
    }
    out["baseline"]["sustainability"] = _sustainability_json(result.baseline)
    if result.ours:
        out["ours"] = {
            "label": result.ours.label,
            "n_games": result.ours.n_games,
            "status": result.ours.status,
            "solve_seconds": result.ours.solve_seconds,
            "seed": result.ours.seed,
            "bundle": result.ours.bundle.to_dict(),
            "sustainability": _sustainability_json(result.ours),
        }
    return out


# ====================================================================
# CLI
# ====================================================================

def run(season_year: int, seed: int, solver_time: float,
        baseline_only: bool, enable_lns_repair: bool,
        warm_start: bool = False,
        out_dir: Optional[Path] = None,
        legacy_bitident: bool = False,
        allow_unpublishable: bool = False,
        mode: str = "publizierbar") -> BacktestResult:
    baseline = load_real_baseline(season_year)
    ours = None
    if not baseline_only:
        if warm_start:
            ours = improve_real_plan(season_year, seed=seed,
                                     legacy_bitident=legacy_bitident,
                                     allow_unpublishable=allow_unpublishable)
        else:
            ours = generate_our_plan(season_year, seed=seed, solver_time=solver_time,
                                     enable_lns_repair=enable_lns_repair)
    result = BacktestResult(season_year=season_year, baseline=baseline, ours=ours)

    out_dir = out_dir or OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"backtest_{season_year}.md"
    html_path = out_dir / f"backtest_{season_year}.html"
    json_path = out_dir / f"backtest_{season_year}.json"
    md_path.write_text(render_markdown(result), encoding="utf-8")
    html_path.write_text(render_html(result), encoding="utf-8")
    json_path.write_text(json.dumps(render_json(result), indent=2, default=str),
                         encoding="utf-8")
    logger.info("B3: Report geschrieben -> %s / .html / .json", md_path)
    # Review-Runde 2 (Punkt 6): Output-Compliance-Report (JSON+MD) je Lauf —
    # fuer den Optimizer-Plan (Baseline = realer Plan beim Warm-Start).
    if ours is not None:
        try:
            from src.run_report import write_run_artifacts
            paths = write_run_artifacts(
                ours.season, out_dir, f"backtest_{season_year}_ours",
                baseline=(baseline.season if warm_start else None),
                mode=mode)
            logger.info("Compliance-Artefakte: %s / %s", paths["json"], paths["md"])
        except Exception as exc:
            logger.warning("Compliance-Artefakte fehlgeschlagen: %s", exc)
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="Backtest: Optimizer vs. echter MLB-Plan")
    p.add_argument("--season", type=int, default=2024, help="Saisonjahr (data/mlb_schedule_<jahr>.json)")
    p.add_argument("--seed", type=int, default=42, help="Generator-Seed (deterministisch)")
    p.add_argument("--solver-time", type=float, default=60.0, help="Max. CP-SAT-Zeit (s)")
    p.add_argument("--baseline-only", action="store_true", help="Nur B1 (reale Baseline) bewerten")
    p.add_argument("--lns-repair", action="store_true", help="AC-2.1.8 LNS-Repair aktivieren (langsamer)")
    p.add_argument("--warm-start", action="store_true",
                   help="Den realen Plan als Startpunkt nehmen und optimieren "
                        "(schlaegt den realen Plan; realistischer Produktionsfall)")
    p.add_argument("--mode", choices=("publizierbar", "forschung"),
                   default="publizierbar",
                   help="Betriebsmodus (Review-Runde 2, Punkt 6): 'publizierbar' "
                        "bricht bei Gate-Verstoß ab; 'forschung' markiert nur.")
    p.add_argument("--legacy-bitident", action="store_true",
                   help="Alt-Verhalten OHNE Regel-Schutzterme (bit-identisch zu "
                        "Messungen vor 2026-06-10). ACHTUNG: Output kann harte "
                        "CBA-Verstoesse enthalten und wird nur markiert, nicht "
                        "abgelehnt. Kein Produktionsmodus.")
    p.add_argument("--allow-unpublishable", action="store_true",
                   help="Publish-Gate-Verstoesse nicht als Fehler werten, sondern "
                        "den Plan markiert ausweisen (nur zur Inspektion).")
    args = p.parse_args()
    run(args.season, args.seed, args.solver_time, args.baseline_only, args.lns_repair,
        warm_start=args.warm_start, legacy_bitident=args.legacy_bitident,
        allow_unpublishable=(args.allow_unpublishable or args.mode == "forschung"),
        mode=args.mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
