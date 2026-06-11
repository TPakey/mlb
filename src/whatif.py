"""What-if Engine — MLB Schedule Impact Analysis (Sprint 2.5) — oeffentliche Fassade.

A21-Refactor (2026-05-31): Die frueheren ~890 LOC dieser Datei wurden in das
Subpackage `src/whatif_core/` aufgeteilt (types / helpers / force / blackout /
compare / impact). Diese Datei bleibt als stabile oeffentliche Fassade: alle
bisherigen Importe `from src.whatif import X` funktionieren unveraendert.
"""
from __future__ import annotations

from .whatif_core import (
    DIMENSION_LABELS,
    DimensionDelta,
    TeamImpact,
    WhatIfContext,
    WhatIfResult,
    _build_deltas,
    _find_free_slot,
    _find_series_for_matchup,
    _flag_constraint_violations,
    _move_games_to_date,
    _occupied_days,
    _replace_games,
    analyze_team_impact,
    whatif_blackout,
    whatif_compare,
    whatif_force_series,
)

__all__ = [
    "DimensionDelta", "WhatIfContext", "WhatIfResult", "TeamImpact",
    "DIMENSION_LABELS",
    "_build_deltas", "_find_free_slot", "_find_series_for_matchup",
    "_flag_constraint_violations", "_move_games_to_date", "_occupied_days",
    "_replace_games",
    "whatif_force_series", "whatif_blackout", "whatif_compare",
    "analyze_team_impact",
]
