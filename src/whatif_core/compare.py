"""whatif_compare (A21-Split). Re-exportiert ueber `src.whatif`."""
from __future__ import annotations

from typing import List

from ..data_loader import Team
from ..pareto_types import compute_pareto_bundle
from ..season import Season
from .types import WhatIfResult
from .helpers import _build_deltas


def whatif_compare(
    season_a: Season,
    season_b: Season,
    teams: List[Team],
    label_a: str = "Plan A",
    label_b: str = "Plan B",
    events=None,
    tv_cfg=None,
    revenue_model=None,
) -> WhatIfResult:
    """Vergleicht zwei unabhängige Saisonpläne in allen 8 Dimensionen.

    Plan A gilt als "Original", Plan B als "Modifiziert". Das Ergebnis
    zeigt das Delta B - A.

    Args:
        season_a:       Referenzplan (wird als Original behandelt).
        season_b:       Alternativplan (wird als Modifiziert behandelt).
        teams:          Alle 30 Teams.
        label_a:        Name des Referenzplans.
        label_b:        Name des Alternativplans.
        events, tv_cfg, revenue_model: Ressourcen für ParetoBundle.

    Returns:
        WhatIfResult mit vollständigem Delta-Bericht.

    Typischer Einsatz:
        >>> result = whatif_compare(pareto_point_balanced.season,
        ...                         pareto_point_travel_min.season,
        ...                         teams, "Balanced", "Travel-Optimiert")
        >>> logger.info(result.summary())
    """
    bundle_a = compute_pareto_bundle(
        season_a, teams, events=events, tv_cfg=tv_cfg, revenue_model=revenue_model,
    )
    bundle_b = compute_pareto_bundle(
        season_b, teams, events=events, tv_cfg=tv_cfg, revenue_model=revenue_model,
    )

    description = (
        f"Vergleich: {label_a} (Referenz) vs. {label_b} (Alternative) — "
        f"Delta = {label_b} minus {label_a}"
    )

    return WhatIfResult(
        scenario_name=f"{label_a} vs. {label_b}",
        description=description,
        original_bundle=bundle_a,
        modified_bundle=bundle_b,
        deltas=_build_deltas(bundle_a, bundle_b),
        modified_season=season_b,
        feasible=True,
        warnings=[],
    )
