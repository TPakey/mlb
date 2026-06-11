"""Lauf-Artefakte: Output-Compliance-Report (JSON + MD) neben den km-Zahlen.

Review-Runde 2 (Punkt 6): Jeder Plan-Lauf legt den vollen Compliance-Report
seines OUTPUTS als maschinen- (JSON) und menschenlesbares (MD) Artefakt ab —
„messen statt behaupten" als Pflicht-Artefakt, nicht als Option. Dazu der
explizite Betriebsmodus:

- **publizierbar** (Default): Gate-Verstoß bricht den Lauf ab (Exit/Raise).
- **forschung**: Gate misst + markiert laut, bricht nicht ab. Für Exploration
  (Pareto-Spielraum, Experimente) — Output trägt den Modus sichtbar im Report.

Reines Reporting, deterministisch, kein RNG.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Dict, Optional

from .season import Season

VALID_MODES = ("publizierbar", "forschung")


def render_compliance_md(rep, gate=None, *, mode: str = "publizierbar",
                         label: str = "") -> str:
    """Kompakter Markdown-Report aus einem ComplianceReport (+ optional Gate)."""
    L = [f"# Output-Compliance-Report — {label or rep.season_year}", ""]
    L.append(f"**Erstellt:** {date.today().isoformat()} · **Saison:** "
             f"{rep.season_year} · **Betriebsmodus:** {mode}")
    L.append("")
    if gate is not None:
        L.append(f"**Publish-Gate:** {gate.summary()}")
        L.append("")
        L.append("> Garantie-Hinweis (Punkt 0b): Im Baseline-Modus bedeutet "
                 "PUBLIZIERBAR „keine Verstoß-Kategorie je Team über der "
                 "Baseline" + '"' + " — NICHT „0 Verstöße" + '"' + ". Geerbte "
                 "as-played-Artefakte bleiben ausgewiesen.")
        L.append("")
    L.append(f"**Hart konform:** {'JA ✓' if rep.is_compliant else 'NEIN ✗'} "
             f"({len(rep.hard_failures)} harte Fehlschläge)")
    L.append("")
    L.append("| Regel | Härte | Ergebnis | Messwert |")
    L.append("|---|---|---|---|")
    for c in rep.checks:
        L.append(f"| {c.rule_id} | {c.rule.severity} | "
                 f"{'PASS ✓' if c.passed else 'FAIL ✗'} | {c.measured} |")
    L.append("")
    fails = [c for c in rep.checks if not c.passed]
    if fails:
        L.append("## Abweichungen im Detail")
        L.append("")
        for c in fails:
            L.append(f"### {c.rule_id} — {c.rule.name}")
            L.append("")
            L.append(f"{c.detail}")
            for o in c.offenders[:15]:
                L.append(f"- {o}")
            if len(c.offenders) > 15:
                L.append(f"- … (+{len(c.offenders) - 15} weitere)")
            L.append("")
    return "\n".join(L)


def write_run_artifacts(
    season: Season,
    out_dir: Path,
    label: str,
    teams_by_id=None,
    *,
    baseline: Optional[Season] = None,
    start_min: Optional[Dict[int, int]] = None,
    events=None,
    mode: str = "publizierbar",
) -> Dict[str, Path]:
    """Schreibt `<label>_compliance.{json,md}` nach ``out_dir``; gibt Pfade zurück."""
    from .compliance import compliance_report
    from .publish_gate import publishable_report

    if teams_by_id is None:
        from .data_loader import load_teams, teams_by_id as _tbi
        teams_by_id = _tbi(load_teams())

    ref = None
    if baseline is not None:
        ref = {}
        for g in baseline.games:
            ref[g.home] = ref.get(g.home, 0) + 1
            ref[g.away] = ref.get(g.away, 0) + 1
    rep = compliance_report(season, teams_by_id=teams_by_id, start_min=start_min,
                            reference_counts=ref, events=events,
                            schedule_kind="original")
    gate = publishable_report(season, teams_by_id, baseline=baseline,
                              start_min=start_min, events=events)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jp = out_dir / f"{label}_compliance.json"
    mp = out_dir / f"{label}_compliance.md"
    payload = rep.to_dict()
    payload["publish_gate"] = {
        "is_publishable": gate.is_publishable,
        "summary": gate.summary(),
        "mode": gate.mode,
        "betriebsmodus": mode,
    }
    import json as _json
    jp.write_text(_json.dumps(payload, indent=2, ensure_ascii=False),
                  encoding="utf-8")
    mp.write_text(render_compliance_md(rep, gate, mode=mode, label=label),
                  encoding="utf-8")
    return {"json": jp, "md": mp}
