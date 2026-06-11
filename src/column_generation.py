"""Column Generation fuer MLB-Schedule (Sprint 2.3a) — oeffentliche Fassade.

A20-Refactor (2026-05-31): Die frueheren ~850 LOC dieser Datei wurden in das
Subpackage `src/colgen/` aufgeteilt (patterns / rmp / pricing / engine / hap),
um die Wartbarkeit zu erhoehen. Diese Datei bleibt als stabile oeffentliche
Fassade bestehen: alle bisherigen Importe `from src.column_generation import X`
funktionieren unveraendert weiter.
"""
from __future__ import annotations

from .colgen import (
    ColumnGenerationLog,
    GlobalHAPResult,
    Pattern,
    PricingResult,
    RMPSolution,
    pacing_to_pattern,
    pricing_subproblem,
    run_column_generation,
    solve_global_hap,
    solve_rmp,
)

__all__ = [
    "Pattern",
    "pacing_to_pattern",
    "RMPSolution",
    "solve_rmp",
    "PricingResult",
    "pricing_subproblem",
    "ColumnGenerationLog",
    "run_column_generation",
    "GlobalHAPResult",
    "solve_global_hap",
]
