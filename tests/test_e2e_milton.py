"""End-to-End-Test: Hurricane Milton vs. historische MLB-Reaktion (AC-2.2.6).

Wir laden das Milton-Szenario aus `data/milton_scenario.json`, lassen unseren
Orchestrator drei Alternativen rechnen, und vergleichen sie gegen die echte
MLB-Loesung (siehe docs/MILTON_GOLD_STANDARD.md).

Ausgabe-Artefakt: `output/e2e_milton_report.json` — der detaillierte
Vergleich. Wird vom Sprint-2.2-Review konsumiert.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from src.disruption import handle_disruption
from src.disruption_types import StadiumBlackout, StrategyKind
from src.generator import GeneratorConfig


ROOT = Path(__file__).resolve().parent.parent


def _load_milton_scenario():
    with (ROOT / "data" / "milton_scenario.json").open(encoding="utf-8") as f:
        return json.load(f)


def _parse_iso(s: str) -> date:
    return date.fromisoformat(s)


@pytest.fixture(scope="module")
def milton_setup():
    """Baut den 2026-Plan und konvertiert das Milton-Szenario in eine StadiumBlackout."""
    from src.datasources import LocalFileAdapter
    from src.generator import generate
    from src.matchup_extractor import extract_matchup_quotas

    adapter = LocalFileAdapter(base_dir="data")
    season_2024 = adapter.fetch_season_schedule(2024)
    quotas = extract_matchup_quotas(season_2024)
    cfg = GeneratorConfig(
        season=2026,
        season_start=date(2026, 3, 26),
        season_end=date(2026, 9, 27),
        all_star_break=(date(2026, 7, 13), date(2026, 7, 16)),
        max_solver_time_seconds=60,
        num_search_workers=1,
        travel_optimizer_iterations=50_000,
    )
    baseline = generate(quotas, cfg).season

    scenario = _load_milton_scenario()
    d = scenario["disruption"]
    disruption = StadiumBlackout(
        home_team=d["home_team"],
        start_date=_parse_iso(d["start_date"]),
        end_date=_parse_iso(d["end_date"]),
        reason=d["reason"],
    )
    return cfg, baseline, disruption, scenario


def _home_games_pct(season, team_id: str, start: date, end: date) -> float:
    """Anteil Heimspiele eines Teams im Fenster [start, end]."""
    in_window = [g for g in season.games if g.involves(team_id) and start <= g.date <= end]
    if not in_window:
        return 0.0
    home_in = sum(1 for g in in_window if g.home == team_id)
    return home_in / len(in_window)


# ====================================================================
# AC-2.2.6: Hurricane-Milton-E2E
# ====================================================================

@pytest.mark.slow
@pytest.mark.integration
def test_AC_2_2_6_milton_end_to_end(milton_setup):
    """End-to-End-Test mit Milton-Szenario: drei valide Alternativen + Report."""
    cfg, baseline, disruption, scenario = milton_setup
    report = handle_disruption(baseline, disruption, cfg)
    assert len(report.alternatives) == 3
    # Mindestens eine Strategie liefert eine substanzielle Antwort
    # (= Spiele veraendern, ohne den Plan zu sprengen)
    nontrivial = [a for a in report.alternatives if len(a.changes) > 0]
    assert len(nontrivial) >= 1, "Keine Strategie liefert eine substantielle Antwort"

    # Output-Artefakt schreiben
    output_dir = ROOT / "output" / "milton_e2e"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Kennzahlen pro Alternative + historischer Vergleich
    report_dict = report.to_dict()

    # Front-Loading-Vergleich gegen historische Realitaet
    historic = scenario["benchmark_dimensions"]
    pre_june_start = disruption.start_date
    pre_june_end = date(2026, 5, 31)
    july_aug_start = date(2026, 7, 1)
    july_aug_end = date(2026, 8, 31)

    history_compare = {
        "historic_home_pct_before_june": historic["home_games_before_june_target_pct"],
        "historic_home_pct_july_august": historic["home_games_july_august_target_pct"],
        "per_alternative": [],
    }
    for alt in report.alternatives:
        pre_june_pct = _home_games_pct(alt.season, "TBR", pre_june_start, pre_june_end) * 100
        jul_aug_pct = _home_games_pct(alt.season, "TBR", july_aug_start, july_aug_end) * 100
        history_compare["per_alternative"].append({
            "strategy": alt.strategy.value,
            "label": alt.label,
            "tbr_home_pct_disruption_to_may": round(pre_june_pct, 1),
            "tbr_home_pct_july_august": round(jul_aug_pct, 1),
            "delta_to_historic_front_load_pct": round(
                pre_june_pct - historic["home_games_before_june_target_pct"], 1),
        })

    full_report = {
        "scenario": scenario,
        "tradeoff_report": report_dict,
        "historic_comparison": history_compare,
    }
    out_path = output_dir / "report.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2, default=str)

    # Markdown-Sidecar fuer menschenlesbare Lesbarkeit
    md_path = output_dir / "report.md"
    with md_path.open("w", encoding="utf-8") as f:
        f.write("# Hurricane Milton — E2E-Report\n\n")
        f.write(f"**Disruption:** {report.disruption_summary}\n\n")
        f.write(f"**Original-Spiele:** {report.original_total_games}\n")
        f.write(f"**Total Runtime:** {report.total_runtime_seconds:.1f} s\n\n")
        f.write("## Alternativen\n\n")
        f.write("| Strategie | Δkm | Affected Teams | ΔRevenue (USD) | ΔFatigue | Change-% | Violations | Runtime |\n")
        f.write("|---|---:|---:|---:|---:|---:|---:|---:|\n")
        for alt in report.alternatives:
            s = alt.score
            f.write(
                f"| {alt.label} | {s.travel_km_delta:+,.0f} | {s.affected_teams} "
                f"| {s.revenue_delta_usd:+,.0f} | {s.fatigue_delta:+.0f} "
                f"| {s.change_pct*100:.1f} % | {s.hard_constraint_violations} "
                f"| {alt.runtime_seconds:.2f} s |\n"
            )
        f.write("\n## Historischer Vergleich (TBR-Heimspielanteil)\n\n")
        f.write(f"MLB-Realitaet 2025 (gold standard):\n")
        f.write(f"- Heim-Quote bis Anfang Juni: **{historic['home_games_before_june_target_pct']} %**\n")
        f.write(f"- Heim-Quote Juli/August:    **{historic['home_games_july_august_target_pct']} %**\n\n")
        f.write("Unsere Alternativen im Disruption-Fenster (TBR):\n\n")
        f.write("| Strategie | Heim-% bis Mai | Heim-% Jul/Aug | Δ zu MLB (Front-Load) |\n")
        f.write("|---|---:|---:|---:|\n")
        for row in history_compare["per_alternative"]:
            f.write(
                f"| {row['label']} | {row['tbr_home_pct_disruption_to_may']:.1f} % "
                f"| {row['tbr_home_pct_july_august']:.1f} % "
                f"| {row['delta_to_historic_front_load_pct']:+.1f} pp |\n"
            )

    # Sanity: Output-Files existieren
    assert out_path.exists()
    assert md_path.exists()
