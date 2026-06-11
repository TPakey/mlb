"""Typed dataclasses fuer den Disruption Handler (Sprint 2.2).

Das Modul definiert das Eingabe-, Ausgabe- und Bewertungs-Schema, das die
drei Strategien (Local Repair, Constrained Re-Generate, Venue-Swap) und der
Orchestrator gemeinsam nutzen.

Designprinzipien:
- typed dataclasses mit validate-im-__post_init__
- frozen wo immer es geht (immutability)
- klare Trennung Disruption-INPUT vs. Alternative-OUTPUT vs. Bewertung
- jedes Schema serialisierbar nach JSON (siehe `to_dict`/`from_dict`)
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from enum import Enum
from typing import Dict, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .season import Season


# ====================================================================
# Disruption-Eingaben
# ====================================================================

class DisruptionKind(str, Enum):
    """Welche Sorte Stoerung."""
    STADIUM_BLACKOUT = "stadium_blackout"
    WEATHER_WINDOW = "weather_window"
    MASS_POSTPONEMENT = "mass_postponement"


@dataclass(frozen=True)
class StadiumBlackout:
    """Ein Stadion ist fuer ein zusammenhaengendes Zeitfenster unbenutzbar.

    Beispiel: Hurricane Milton — Tropicana Field 2025-04-01 bis 2025-09-30.
    Alle Heimspiele dieses Teams im Fenster sind betroffen.
    """
    home_team: str                       # Team-ID des Heimteams
    start_date: date                     # inklusiv
    end_date: date                       # inklusiv
    reason: str = ""                     # menschenlesbar, fuer Reports

    kind: DisruptionKind = field(default=DisruptionKind.STADIUM_BLACKOUT, init=False)

    def __post_init__(self):
        if not self.home_team or len(self.home_team) < 2:
            raise ValueError(f"Ungueltige Team-ID: {self.home_team!r}")
        if self.end_date < self.start_date:
            raise ValueError(
                f"end_date {self.end_date} liegt vor start_date {self.start_date}"
            )

    def affects(self, home: str, game_date: date) -> bool:
        return home == self.home_team and self.start_date <= game_date <= self.end_date


@dataclass(frozen=True)
class WeatherWindow:
    """Wetter-/Naturkatastrophen-Fenster fuer eine Stadt: alle Spiele in
    dieser Stadt im Fenster sind betroffen, unabhaengig vom Heimteam.

    Beispiel: extreme Hitzewelle Phoenix, AZ — 2026-07-10 bis 2026-07-15.
    Da nur ein Team pro Stadt ist (Diamondbacks), in der Praxis aehnlich
    zu StadiumBlackout, aber semantisch unterschiedlich (Wetter, nicht
    Stadion-Schaden).
    """
    city: str                            # Stadt-Identifier (matched mit teams.json)
    start_date: date
    end_date: date
    severity: int = 3                    # 1 (mild) .. 5 (massiv)
    reason: str = ""

    kind: DisruptionKind = field(default=DisruptionKind.WEATHER_WINDOW, init=False)

    def __post_init__(self):
        if self.end_date < self.start_date:
            raise ValueError(
                f"end_date {self.end_date} liegt vor start_date {self.start_date}"
            )
        if not 1 <= self.severity <= 5:
            raise ValueError(f"severity muss in 1..5 sein, ist {self.severity}")


@dataclass(frozen=True)
class MassPostponement:
    """Eine Liste konkreter Spiele wird komplett abgesagt und muss
    neu eingeplant werden. Beispiel: pandemiebedingte Verschiebungen,
    Bundes-/Trauerregelung etc.
    """
    game_pks: Tuple[int, ...]            # Spiele, die betroffen sind
    reason: str = ""

    kind: DisruptionKind = field(default=DisruptionKind.MASS_POSTPONEMENT, init=False)

    def __post_init__(self):
        if not self.game_pks:
            raise ValueError("game_pks darf nicht leer sein")


# ====================================================================
# Score-Bundle pro Alternative
# ====================================================================

@dataclass(frozen=True)
class ScoreBundle:
    """Tradeoff-Bewertung einer einzelnen Alternative.

    Alle Werte sind DELTAS gegen den Original-Plan (positiv = schlechter
    fuer km/fatigue/violations, positiv = besser fuer revenue_delta_usd).
    """
    travel_km_delta: float               # zusaetzliche km gegenueber Original
    affected_teams: int                  # Anzahl Teams, deren Plan sich aendert
    revenue_delta_usd: float             # erwarteter Revenue-Δ (negativ = Verlust)
    fatigue_delta: float                 # Player-Fatigue-Score-Δ (siehe player_fatigue)
    change_pct: float                    # Anteil geaenderter Spiele (0..1)
    hard_constraint_violations: int = 0  # MUSS 0 sein in validen Alternativen

    def is_valid(self) -> bool:
        return self.hard_constraint_violations == 0


# ====================================================================
# Alternative-Ausgabe
# ====================================================================

class StrategyKind(str, Enum):
    """Welche Repair-Strategie diese Alternative produziert hat."""
    LOCAL_REPAIR = "local_repair"                  # Strategie A
    CONSTRAINED_REGENERATE = "constrained_regen"   # Strategie B
    VENUE_SWAP = "venue_swap"                      # Strategie C


@dataclass(frozen=True)
class GameChange:
    """Eine einzelne Aenderung gegenueber dem Original.

    Drei Aenderungstypen werden unterstuetzt:
    - move:   Spiel bleibt gleich, aber neues Datum
    - swap:   Heim/Auswaerts vertauscht, ggf. neues Datum/Venue
    - cancel: Spiel ist im neuen Plan nicht mehr enthalten
    """
    original_game_pk: int
    change_type: str                     # "move" | "swap" | "cancel" | "add"
    new_date: Optional[date] = None
    new_home: Optional[str] = None
    new_away: Optional[str] = None
    note: str = ""


@dataclass(frozen=True)
class Alternative:
    """Eine vollstaendige Alternative-Loesung."""
    strategy: StrategyKind
    label: str                           # menschenlesbar, z.B. "Postpone-to-Next-Off-Day"
    season: "Season"                     # der komplette neue Plan (siehe season.py)
    changes: Tuple[GameChange, ...]      # Diff gegen Original-Plan
    score: ScoreBundle
    runtime_seconds: float
    notes: str = ""


# ====================================================================
# Tradeoff-Report (Orchestrator-Ausgabe)
# ====================================================================

@dataclass(frozen=True)
class TradeoffReport:
    """Vollstaendige Antwort des Disruption-Handlers."""
    disruption_summary: str              # menschenlesbare Beschreibung
    original_total_games: int
    alternatives: Tuple[Alternative, ...]
    total_runtime_seconds: float

    def best_by(self, metric: str) -> Optional[Alternative]:
        """Liefere die Alternative mit besten Wert fuer eine Metrik.

        Unterstuetzt: 'travel_km', 'revenue', 'fatigue', 'change_pct'.
        Bei Tie: deterministisch nach Strategy-Reihenfolge (A < B < C).
        """
        if not self.alternatives:
            return None
        key_map = {
            "travel_km": lambda a: a.score.travel_km_delta,
            "revenue": lambda a: -a.score.revenue_delta_usd,  # mehr ist besser
            "fatigue": lambda a: a.score.fatigue_delta,
            "change_pct": lambda a: a.score.change_pct,
        }
        if metric not in key_map:
            raise ValueError(f"Unbekannte Metrik: {metric}")
        return min(self.alternatives, key=key_map[metric])

    def to_dict(self) -> Dict:
        """JSON-serialisierbare Repraesentation (ohne Season-Objekte)."""
        return {
            "disruption_summary": self.disruption_summary,
            "original_total_games": self.original_total_games,
            "total_runtime_seconds": self.total_runtime_seconds,
            "alternatives": [
                {
                    "strategy": a.strategy.value,
                    "label": a.label,
                    "runtime_seconds": a.runtime_seconds,
                    "score": asdict(a.score),
                    "num_changes": len(a.changes),
                    "notes": a.notes,
                }
                for a in self.alternatives
            ],
        }
