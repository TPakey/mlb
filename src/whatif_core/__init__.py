"""whatif_core — Implementierungs-Subpackage der What-if-Engine (Sprint 2.5; A21).

Aufgeteilt aus der frueheren `whatif.py` (~890 LOC) in fokussierte Module:
types / helpers / force / blackout / compare / impact. Oeffentliche API
unveraendert ueber `src.whatif` re-exportiert.
"""
from .types import DimensionDelta, WhatIfContext, WhatIfResult
from .helpers import (
    DIMENSION_LABELS,
    _build_deltas,
    _find_free_slot,
    _find_series_for_matchup,
    _flag_constraint_violations,
    _move_games_to_date,
    _occupied_days,
    _replace_games,
)
from .force import whatif_force_series
from .blackout import whatif_blackout
from .compare import whatif_compare
from .impact import TeamImpact, analyze_team_impact

__all__ = [
    "DimensionDelta", "WhatIfContext", "WhatIfResult", "TeamImpact",
    "DIMENSION_LABELS",
    "_build_deltas", "_find_free_slot", "_find_series_for_matchup",
    "_flag_constraint_violations", "_move_games_to_date", "_occupied_days",
    "_replace_games",
    "whatif_force_series", "whatif_blackout", "whatif_compare",
    "analyze_team_impact",
]
