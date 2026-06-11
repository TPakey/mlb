"""colgen — Implementierungs-Subpackage der Column Generation (Sprint 2.3a; A20).

Aufgeteilt aus der frueheren `column_generation.py` (~850 LOC) in fokussierte
Module: patterns / rmp / pricing / engine / hap. Die oeffentliche API wird
unveraendert ueber `src.column_generation` re-exportiert — bestehende Importe
(`from src.column_generation import solve_global_hap`, ...) bleiben stabil.
"""
from .patterns import Pattern, pacing_to_pattern
from .rmp import RMPSolution, solve_rmp
from .pricing import PricingResult, pricing_subproblem
from .engine import ColumnGenerationLog, run_column_generation
from .hap import GlobalHAPResult, solve_global_hap

__all__ = [
    "Pattern", "pacing_to_pattern",
    "RMPSolution", "solve_rmp",
    "PricingResult", "pricing_subproblem",
    "ColumnGenerationLog", "run_column_generation",
    "GlobalHAPResult", "solve_global_hap",
]
