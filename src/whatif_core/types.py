"""What-if Ergebnis-Typen (Sprint 2.5; A21-Subpackage-Split).

DimensionDelta, WhatIfContext, WhatIfResult. Re-exportiert ueber `src.whatif`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..data_loader import Team
from ..generator import GeneratorConfig
from ..pareto_types import ParetoBundle
from ..season import Season


@dataclass(frozen=True)
class DimensionDelta:
    """Delta einer einzelnen Score-Dimension."""
    name: str
    label: str
    unit: str
    original: float
    modified: float
    delta: float           # modified - original (negativ = besser wenn minimize)
    delta_pct: float       # delta / original * 100 (0 wenn original == 0)
    direction: str         # "better" | "worse" | "neutral"
    minimize: bool

    @property
    def is_better(self) -> bool:
        return self.direction == "better"

    @property
    def is_worse(self) -> bool:
        return self.direction == "worse"

    def __str__(self) -> str:
        sign = "+" if self.delta > 0 else ""
        unit = f" {self.unit}" if self.unit else ""
        pct = f" ({sign}{self.delta_pct:+.1f}%)" if self.original != 0 else ""
        icon = {"better": "✓", "worse": "✗", "neutral": "~"}[self.direction]
        return f"  {icon} {self.label:<22} {self.original:>14.1f} → {self.modified:>14.1f}{unit}{pct}"


@dataclass(frozen=True)
class WhatIfContext:
    """Zentraler Kontext-Container für die What-if-API (Audit A19, Sprint A-5).

    Bündelt die wiederkehrenden Parameter (teams, cfg, events, tv_cfg,
    revenue_model), die bisher als separate Kwargs an jede What-if-Funktion
    durchgereicht wurden. Bestehende Funktionen behalten ihre Einzelparameter
    (Backward-Compat); `WhatIfContext.unpack()` liefert das Tuple für sie.

    Beispiel-Nutzung in Aufrufer-Code (Sprint 2.12+):
        ctx = WhatIfContext.from_defaults(teams=teams, cfg=cfg)
        res = whatif_force_series(season, ctx.teams, ctx.cfg, "NYY", "BOS", ...,
                                  events=ctx.events, tv_cfg=ctx.tv_cfg,
                                  revenue_model=ctx.revenue_model)
    """
    teams: List["Team"]
    cfg: "GeneratorConfig"
    events: Optional[List] = None
    tv_cfg: Optional[object] = None
    revenue_model: Optional[object] = None

    @classmethod
    def from_defaults(cls, teams: List["Team"], cfg: "GeneratorConfig"
                      ) -> "WhatIfContext":
        """Lazy-lädt die Default-Ressourcen aus data/."""
        from ..event_conflicts import load_local_events
        from ..tv_slots import TvSlotConfig
        from ..revenue import RevenueModel
        return cls(
            teams=teams,
            cfg=cfg,
            events=load_local_events(),
            tv_cfg=TvSlotConfig.load(),
            revenue_model=RevenueModel.load(),
        )

    def unpack(self):
        """Tuple-Sicht für die bestehenden Funktions-Signaturen."""
        return self.teams, self.cfg, self.events, self.tv_cfg, self.revenue_model


@dataclass
class WhatIfResult:
    """Vollständiges Ergebnis einer What-if-Analyse."""
    scenario_name: str
    description: str
    original_bundle: ParetoBundle
    modified_bundle: ParetoBundle
    deltas: List[DimensionDelta]
    modified_season: Season
    feasible: bool         # True wenn alle Konflikte aufgelöst werden konnten
    warnings: List[str] = field(default_factory=list)

    # ---- Abfrage-Helfer ----

    @property
    def n_better(self) -> int:
        return sum(1 for d in self.deltas if d.is_better)

    @property
    def n_worse(self) -> int:
        return sum(1 for d in self.deltas if d.is_worse)

    @property
    def net_travel_delta_km(self) -> float:
        return self._delta_for("travel_km")

    @property
    def net_revenue_delta_usd(self) -> float:
        return self._delta_for("revenue_usd")

    def _delta_for(self, dim: str) -> float:
        for d in self.deltas:
            if d.name == dim:
                return d.delta
        return 0.0

    def summary(self) -> str:
        """Kompakter Text-Report für stdout."""
        lines = [
            f"\n{'═' * 70}",
            f"  WHAT-IF: {self.scenario_name}",
            f"  {self.description}",
            f"{'─' * 70}",
            f"  {'Dimension':<22}  {'Original':>14}  {'Modifiziert':>14}  Delta",
            f"{'─' * 70}",
        ]
        for d in self.deltas:
            lines.append(str(d))
        lines += [
            f"{'─' * 70}",
            f"  Besser: {self.n_better}  Schlechter: {self.n_worse}  "
            f"Neutral: {len(self.deltas) - self.n_better - self.n_worse}",
        ]
        if self.warnings:
            lines.append(f"{'─' * 70}")
            for w in self.warnings:
                lines.append(f"  ⚠  {w}")
        if not self.feasible:
            lines.append("  ✗  NICHT FEASIBEL — nicht alle Konflikte konnten aufgelöst werden.")
        lines.append(f"{'═' * 70}\n")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "scenario_name": self.scenario_name,
            "description": self.description,
            "feasible": self.feasible,
            "warnings": self.warnings,
            "n_better": self.n_better,
            "n_worse": self.n_worse,
            "original_bundle": self.original_bundle.to_dict(),
            "modified_bundle": self.modified_bundle.to_dict(),
            "deltas": [
                {
                    "name": d.name,
                    "label": d.label,
                    "original": d.original,
                    "modified": d.modified,
                    "delta": d.delta,
                    "delta_pct": d.delta_pct,
                    "direction": d.direction,
                }
                for d in self.deltas
            ],
        }


# ====================================================================
# Bundle-Differenz berechnen
