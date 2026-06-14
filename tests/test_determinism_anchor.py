"""Determinismus-Anker als Regressionstest (Finalisierung Punkt 4).

Bisher lebte der Anker nur in der Doku ("Legacy-Anker 1680131 weiterhin
exakt") — nicht prüfbar, also nicht belastbar. Dieser Test nagelt ihn fest.

Definition des Ankers (kanonisch, wie in docs/REVIEW_2026-06-10): der reale
2024-Plan (as-played), optimiert im LEGACY-Modus (ohne Regel-Schutzterme,
``--legacy-bitident``), 200 000 Iterationen, Seed 42 → reproduzierbare
final_km. Der SA nutzt ``random.Random(seed)`` (Mersenne-Twister, plattform-
und versionsstabil), daher ist der Wert über Maschinen hinweg identisch,
solange Code + eingefrorene Daten (MANIFEST) gleich sind.

WICHTIGER BEFUND (Finalisierung): Der in der Doku genannte Wert **1680131**
reproduziert auf dem aktuellen Stand NICHT mehr — kanonisch (zweifach, zwei
Codepfade) ergibt sich **1672794**. Der alte Wert ist also gedriftet
(vermutlich vor dem Bundle-HEAD), und die Behauptung „weiterhin exakt" war
nicht mehr korrekt. Wir verankern den TATSÄCHLICH reproduzierenden Wert; die
Doku ist entsprechend korrigiert (docs/FINALIZATION.md).
"""
from __future__ import annotations

from tools.backtest import improve_real_plan

# Tatsächlich reproduzierender Anker auf dem aktuellen, committeten Stand.
LEGACY_ANCHOR_2024_KM = 1_672_794
LEGACY_SEED = 42
LEGACY_ITERATIONS = 200_000


def test_legacy_determinism_anchor_2024():
    """Legacy 2024 / 200k / Seed 42 → exakt der verankerte km-Wert."""
    ev = improve_real_plan(2024, seed=LEGACY_SEED, iterations=LEGACY_ITERATIONS,
                           legacy_bitident=True)
    assert round(ev.travel.total_km) == LEGACY_ANCHOR_2024_KM, (
        f"Determinismus-Anker gebrochen: {round(ev.travel.total_km)} != "
        f"{LEGACY_ANCHOR_2024_KM}. Entweder Determinismus verletzt oder eine "
        f"Änderung hat die SA-Trajektorie verschoben — bewusst neu verankern.")


def test_anchor_run_is_bit_identical():
    """Zwei Läufe mit gleichem Seed → bit-identische km (Determinismus)."""
    a = improve_real_plan(2024, seed=LEGACY_SEED, iterations=80_000,
                          legacy_bitident=True)
    b = improve_real_plan(2024, seed=LEGACY_SEED, iterations=80_000,
                          legacy_bitident=True)
    assert a.travel.total_km == b.travel.total_km
