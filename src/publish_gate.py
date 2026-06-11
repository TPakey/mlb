"""Publish-Gate — harte Abnahmeprüfung für JEDEN Plan-Output (Review-Fix P0-1/P0-2).

Hintergrund (docs/REVIEW_2026-06-10_INDEPENDENT_AI.md): Der Produktionspfad
optimierte und meldete km-Ersparnis, ohne den eigenen Output je gegen das eigene
Compliance-Tooling zu messen — Ergebnis waren stille harte CBA-Verstöße
(V(C)(11), V(C)(13), Reise-Envelope). Dieses Modul macht die Messung zur Pflicht:

    gate = publishable_report(optimized, teams_by_id, baseline=real)
    if not gate.is_publishable: <nicht als Ergebnis ausweisen / abbrechen>

Semantik
--------
- **Ohne Baseline (strict):** Plan muss `compliance_report(...).is_compliant`
  bestehen UND `original_schedule_violations(...) == []` (V(C)(13)/(14)/(15)).
  Maßstab für green-field/Original-Pläne.
- **Mit Baseline (warm-start):** Der Optimierer startet von einem realen
  **as-played**-Plan, der selbst Artefakt-Verstöße trägt (Makeups, Relokationen;
  `finding-as-played-data`) und die er nicht beheben kann. Das Gate verlangt
  deshalb: **kein einziger NEUER Verstoß gegenüber der Baseline** —
  (a) keine harte Regel, die auf der Baseline bestand, darf auf dem Output
  fallen; (b) je (Strukturregel, Team) darf die Verstoß-Anzahl nicht über die
  Baseline steigen. Geerbte Verstöße werden getrennt ausgewiesen, nicht
  verschwiegen. SCHED-162 wird mit exakten Referenz-Counts der Baseline geprüft
  (kein Spiel verloren/dupliziert).

  **Grenze dieser Garantie (Punkt 0b, absichtlich prominent):** „PUBLIZIERBAR"
  im Baseline-Modus heißt NICHT „0 Verstöße". Es heißt: *keine Verstoß-Kategorie
  je Team steigt über die Baseline.* Geerbte Artefakt-Verstöße bleiben bestehen,
  und ein geerbtes V(C)(13)-Fenster kann team-intern die POSITION wechseln
  (gleiches Team, gleiche Kategorie, anderes Datum). Wer „0 Verstöße" behaupten
  will, braucht den strikten Modus (baseline=None) auf einem Original-Plan —
  verifiziert per Messung (siehe REVIEW-Addendum Runde 2), nicht per Behauptung.

Reines Messen/Reporting — verändert keinen Plan, kein RNG, deterministisch.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .season import Season


class UnpublishableScheduleError(RuntimeError):
    """Ein Plan hat das Publish-Gate nicht bestanden (harte Regelverstöße)."""


@dataclass(frozen=True)
class PublishGate:
    """Ergebnis der Abnahmeprüfung."""
    is_publishable: bool
    new_hard_failures: List[str] = field(default_factory=list)        # Regel-IDs
    inherited_hard_failures: List[str] = field(default_factory=list)  # Regel-IDs
    new_structural: List[str] = field(default_factory=list)           # je (Regel, Team)
    inherited_structural_count: int = 0
    mode: str = "strict"   # "strict" | "baseline"

    def summary(self) -> str:
        if self.is_publishable:
            if self.mode == "baseline":
                # WICHTIG (Review Runde 2, Punkt 0b): Diese Garantie ist
                # bewusst SCHWAECHER als "0 Verstoesse" — und das steht hier
                # absichtlich im Output, damit daraus nie wieder still ein
                # "voll konform"-Claim wird.
                return ("PUBLIZIERBAR ✓ — Garantie: keine Verstoss-Kategorie je "
                        f"Team über Baseline (NICHT '0 Verstöße': "
                        f"{self.inherited_structural_count} geerbte as-played-"
                        f"Artefakte bleiben, Fenster können team-intern wandern; "
                        f"{len(self.inherited_hard_failures)} geerbte harte "
                        f"Baseline-Fails)")
            return ("PUBLIZIERBAR ✓ — strikt: 0 harte und 0 strukturelle "
                    "Verstöße (Original-Maßstab)")
        parts = []
        if self.new_hard_failures:
            parts.append(f"harte Regel(n) verletzt: {', '.join(self.new_hard_failures)}")
        if self.new_structural:
            parts.append(f"{len(self.new_structural)} neue Strukturverstöße "
                         f"(z. B. {self.new_structural[0]})")
        return "NICHT PUBLIZIERBAR ✗ — " + "; ".join(parts)


def _structural_counts(season: Season,
                       start_min: Optional[Dict[int, int]] = None) -> Counter:
    """Zähler je (Regel, Team) für V(C)(13)/(14)/(15)."""
    from .schedule_rules import check_offday_distribution, check_doubleheader_limits
    viols = (check_offday_distribution(season)
             + check_doubleheader_limits(season, start_min=start_min))
    return Counter((v.rule, v.team) for v in viols)


def _team_game_counts(season: Season) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for g in season.games:
        counts[g.home] = counts.get(g.home, 0) + 1
        counts[g.away] = counts.get(g.away, 0) + 1
    return counts


def publishable_report(
    season: Season,
    teams_by_id=None,
    *,
    baseline: Optional[Season] = None,
    start_min: Optional[Dict[int, int]] = None,
    events=None,
) -> PublishGate:
    """Misst den Plan mit dem projekteigenen Compliance-Tooling (P0-1-Fix).

    ``baseline``: der Input-Plan eines Warm-Starts (as-played). Ohne Baseline
    gilt der strikte Maßstab (Original-/green-field-Plan).
    ``events``: LocalEvent-Liste → aktiviert den harten VENUE-AVAIL-Check
    (Review-Runde 2, Punkt 2 — vorher war die harte Regel im Gate nie aktiv).
    """
    from .compliance import compliance_report

    if teams_by_id is None:
        from .data_loader import load_teams, teams_by_id as _tbi
        teams_by_id = _tbi(load_teams())

    if baseline is not None:
        ref_counts = _team_game_counts(baseline)
        rep_out = compliance_report(season, teams_by_id=teams_by_id,
                                    reference_counts=ref_counts,
                                    start_min=start_min, schedule_kind="original",
                                    events=events)
        rep_base = compliance_report(baseline, teams_by_id=teams_by_id,
                                     reference_counts=ref_counts,
                                     start_min=start_min, schedule_kind="as_played",
                                     events=events)
        base_failed = {c.rule_id for c in rep_base.hard_failures}
        out_failed = [c.rule_id for c in rep_out.hard_failures]
        new_hard = [r for r in out_failed if r not in base_failed]
        inherited_hard = [r for r in out_failed if r in base_failed]

        out_struct = _structural_counts(season, start_min)
        base_struct = _structural_counts(baseline, start_min)
        new_structural = [
            f"{rule} {team}: {n} > Baseline {base_struct.get((rule, team), 0)}"
            for (rule, team), n in sorted(out_struct.items())
            if n > base_struct.get((rule, team), 0)
        ]
        inherited = sum(min(n, base_struct.get(k, 0)) for k, n in out_struct.items())
        return PublishGate(
            is_publishable=not new_hard and not new_structural,
            new_hard_failures=new_hard,
            inherited_hard_failures=inherited_hard,
            new_structural=new_structural,
            inherited_structural_count=inherited,
            mode="baseline",
        )

    # strict: Original-/green-field-Maßstab
    rep = compliance_report(season, teams_by_id=teams_by_id,
                            start_min=start_min, schedule_kind="original",
                            events=events)
    hard = [c.rule_id for c in rep.hard_failures]
    struct = _structural_counts(season, start_min)
    structural = [f"{rule} {team}: {n}" for (rule, team), n in sorted(struct.items())]
    return PublishGate(
        is_publishable=not hard and not structural,
        new_hard_failures=hard,
        new_structural=structural,
        mode="strict",
    )


def assert_publishable(
    season: Season,
    teams_by_id=None,
    *,
    baseline: Optional[Season] = None,
    start_min: Optional[Dict[int, int]] = None,
    context: str = "",
) -> PublishGate:
    """Wie ``publishable_report``, wirft aber ``UnpublishableScheduleError``,
    wenn der Plan nicht publizierbar ist. Rückgabe: das Gate (für Logging)."""
    gate = publishable_report(season, teams_by_id, baseline=baseline,
                              start_min=start_min)
    if not gate.is_publishable:
        prefix = f"[{context}] " if context else ""
        raise UnpublishableScheduleError(
            f"{prefix}{gate.summary()} — Output darf nicht als Ergebnis "
            f"ausgewiesen werden (Review-Fix P0-1; "
            f"docs/REVIEW_2026-06-10_INDEPENDENT_AI.md).")
    return gate
