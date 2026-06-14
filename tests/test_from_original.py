"""End-to-End-Test des HEADLINE-WORKFLOWS (Finalisierung, Punkt 1).

Die zentrale Demo des Tools — *publizierten Originalplan laden → optimieren →
Publish-Gate → Δkm* — muss ein erstklassiger, auf Knopfdruck reproduzierbarer
Entry-Point sein, kein Ad-hoc-Skript. Vor der Finalisierung konnten weder
``tools/backtest`` noch ``src/main`` den 2026-Originalplan überhaupt laden
(beide nur as-played ``data/mlb_schedule_<jahr>.json``; 2026 existiert dort
nicht). Dieser Test nagelt den Pfad fest:

  * der Originalplan 2026 ist über ``--from-original`` ladbar (2430 Spiele),
  * der optimierte Output passiert das Publish-Gate (PASS), und
  * er spart Reise-km gegenüber dem Original (Δkm < 0).

Iterationszahl bewusst niedrig gehalten (CI-tauglich, ~2 s). Der ausgewiesene
Headline-Wert (−1,8 %) entsteht erst mit 3–6 M Iterationen auf echter Hardware;
hier geht es um die *Reproduzierbarkeit der Kette*, nicht um die km-Tiefe.
"""
from __future__ import annotations

import pytest

from tools.backtest import improve_real_plan, load_real_baseline

YEAR = 2026
ITERATIONS = 150_000  # CI-schnell; Gate-Garantie ist iterationsunabhängig (λ=1e6)


@pytest.fixture(scope="module")
def baseline():
    return load_real_baseline(YEAR, from_original=True)


def test_original_plan_is_loadable(baseline):
    """2026-Originalplan ist über den committeten Pfad ladbar (vorher unmöglich)."""
    assert baseline.n_games == 2430
    assert "Original" in baseline.label
    assert baseline.travel.total_km > 0


def test_from_original_headline_passes_gate_and_saves_km(baseline):
    """Headline-Kette: optimieren → Gate PASS → Δkm < 0, auf Knopfdruck.

    ``improve_real_plan`` wirft ``UnpublishableScheduleError``, wenn das Gate
    NICHT besteht (Default ``allow_unpublishable=False``) — der Test besteht
    also nur, wenn das Gate real PASST.
    """
    ours = improve_real_plan(YEAR, seed=42, iterations=ITERATIONS,
                             from_original=True)
    # Gate bestanden (sonst wäre oben eine Exception geflogen):
    assert "NICHT PUBLIZIERBAR" not in ours.label
    # Verbesserung gegenüber dem Originalplan:
    delta = ours.travel.total_km - baseline.travel.total_km
    assert delta < 0, f"Erwartet Δkm < 0, gemessen {delta:+.0f} km"


def test_from_original_is_deterministic():
    """Gleicher Seed → bit-identische Reise-km (Determinismus-Versprechen)."""
    a = improve_real_plan(YEAR, seed=42, iterations=80_000, from_original=True)
    b = improve_real_plan(YEAR, seed=42, iterations=80_000, from_original=True)
    assert round(a.travel.total_km, 3) == round(b.travel.total_km, 3)
