"""Pareto-Profile — konfigurierbare Optimierungsgewichte (Hauptpfad).

Hinweis (Sprint 2.8 / M10): Das alte 7-dimensionale **TradeoffProfile**
(Sprint 0/1) wurde nach `src/legacy/tradeoff_profiles.py` verschoben und wird
nur noch vom Legacy-Pfad verwendet. Dieses Modul enthält ausschliesslich das
aktive **ParetoProfile**-System.

**ParetoProfile** (Sprint 2.3b, aktiv):
Gewichte für das neue 8-dimensionale ParetoBundle-System. Alle Gewichte
sind in km-Äquivalent-Einheiten:
  - w_travel     [km/km]        — 1.0 = jedes Reise-km zählt mit Faktor 1
  - w_revenue    [km/USD]       — negativ: Revenue-Zuwachs senkt Energie
  - w_fatigue    [km/pt]        — Fatigue-Score in km umgerechnet
  - w_away_streak [km/day]      — pro Tag konsekutiver Auswärts-Streak
  - w_off_day    [km/var]       — Off-Day-Varianz (dimensionslose Varianz)
  - w_tv         [km/score]     — negativ: TV-Score erhöht senkt Energie
  - w_friction   [km/sev]       — Event-Friction-Severity → km
  - violations_penalty [km]     — Strafe pro Constraint-Verletzung

Kalibrierung der Referenz-Skalen (Saison-typisch):
  travel_km       ~2,000,000 km
  revenue_usd     ~8,000,000,000 USD
  fatigue_score   ~5,000–15,000 Punkte
  max_away_streak ~8–13 Tage
  off_day_variance ~0.001–0.015
  tv_slot_score   ~2,000–3,500 Punkte
  event_friction  ~50–200 Severity-Punkte
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from .pareto_types import ParetoBundle


# ====================================================================
# ParetoProfile — Sprint 2.3b (8-Dimensionales System, Hauptpfad)
# ====================================================================

@dataclass(frozen=True)
class ParetoProfile:
    """Gewichtungsvektor für die 8-dimensionale ParetoBundle-Optimierung.

    Alle Gewichte in km-Äquivalent-Einheiten (see Modul-Docstring).
    Die compute_energy()-Methode liefert einen Energie-Wert in km,
    kompatibel mit dem SA-Optimizer (start_temperature ~1500).
    """
    name: str
    description: str

    # Gewichte (km-Äquivalent)
    w_travel: float       = 1.0         # km/km
    w_revenue: float      = -5e-7       # km/USD  (negativ: mehr Revenue → weniger Energie)
    w_fatigue: float      = 20.0        # km/fatigue-point
    w_away_streak: float  = 5000.0      # km/day (pro Tag Worst-Case-Streak)
    w_off_day: float      = 20_000_000.0  # km/variance (Varianz ist sehr klein)
    w_tv: float           = -200.0      # km/tv-score-point (negativ: höherer Score → weniger Energie)
    w_friction: float     = 500.0       # km/severity-point
    violations_penalty: float = 1_000_000_000.0  # km pro Verletzung (faktisch unendlich)

    def compute_energy(self, bundle: "ParetoBundle") -> float:
        """Berechnet die gewichtete SA-Energie in km-Äquivalent.

        Niedrigere Energie = besserer Plan (SA minimiert).
        """
        return (
            self.w_travel        * bundle.travel_km
            + self.w_revenue     * bundle.revenue_usd
            + self.w_fatigue     * bundle.fatigue_score
            + self.w_away_streak * bundle.max_away_streak
            + self.w_off_day     * bundle.off_day_variance
            + self.w_tv          * bundle.tv_slot_score
            + self.w_friction    * bundle.event_friction
            + self.violations_penalty * bundle.constraint_violations
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def free(cls, name: str = "custom", description: str = "Free Profile",
             **weights) -> "ParetoProfile":
        """Erstellt ein freies Profil mit beliebigen Gewichten.

        Fehlende Gewichte werden aus dem 'balanced'-Profil übernommen.

        Beispiel:
            ParetoProfile.free(w_travel=3.0, w_tv=-500.0)
        """
        base = PARETO_PROFILES["balanced"]
        return cls(
            name=name,
            description=description,
            w_travel=weights.get("w_travel", base.w_travel),
            w_revenue=weights.get("w_revenue", base.w_revenue),
            w_fatigue=weights.get("w_fatigue", base.w_fatigue),
            w_away_streak=weights.get("w_away_streak", base.w_away_streak),
            w_off_day=weights.get("w_off_day", base.w_off_day),
            w_tv=weights.get("w_tv", base.w_tv),
            w_friction=weights.get("w_friction", base.w_friction),
            violations_penalty=weights.get("violations_penalty", base.violations_penalty),
        )


# ====================================================================
# Named Pareto-Profile (Sprint 2.3b)
# ====================================================================

PARETO_PROFILES: Dict[str, ParetoProfile] = {

    "balanced": ParetoProfile(
        name="Balanced",
        description=(
            "Gleichgewichteter Trade-off über alle 8 Dimensionen. "
            "Sinnvolle Default-Wahl, wenn keine politische Vorgabe existiert."
        ),
        w_travel=1.0, w_revenue=-5e-7, w_fatigue=20.0,
        w_away_streak=5000.0, w_off_day=20_000_000.0,
        w_tv=-200.0, w_friction=500.0,
    ),

    "travel_min": ParetoProfile(
        name="Travel Minimizer",
        description=(
            "Minimiert die Gesamtreisedistanz (CO₂, Kosten). "
            "Revenue und TV-Slots treten in den Hintergrund."
        ),
        w_travel=5.0, w_revenue=-1e-7, w_fatigue=5.0,
        w_away_streak=1000.0, w_off_day=5_000_000.0,
        w_tv=-50.0, w_friction=100.0,
    ),

    "revenue_max": ParetoProfile(
        name="Revenue Max",
        description=(
            "Maximiert Gate-Revenue und TV-Attraktivität. "
            "Reisedistanz und Fatigue treten in den Hintergrund."
        ),
        w_travel=0.3, w_revenue=-3e-6, w_fatigue=5.0,
        w_away_streak=500.0, w_off_day=2_000_000.0,
        w_tv=-800.0, w_friction=100.0,
    ),

    "player_friendly": ParetoProfile(
        name="Player-Friendly",
        description=(
            "Minimiert Spieler-Fatigue und konsekutive Auswärtsreisen. "
            "CBA-nahe Constraints werden stark priorisiert."
        ),
        w_travel=0.5, w_revenue=-2e-7, w_fatigue=100.0,
        w_away_streak=25000.0, w_off_day=50_000_000.0,
        w_tv=-100.0, w_friction=200.0,
    ),

    "tv_optimized": ParetoProfile(
        name="TV Optimized",
        description=(
            "Maximiert TV-Slot-Attraktivität: Marquee-Matchups an Premium-Tagen "
            "(Samstag/Sonntag Night), Revenue als sekundäres Ziel."
        ),
        w_travel=0.2, w_revenue=-1e-6, w_fatigue=5.0,
        w_away_streak=500.0, w_off_day=2_000_000.0,
        w_tv=-2000.0, w_friction=50.0,
    ),

    "city_friendly": ParetoProfile(
        name="City-Friendly",
        description=(
            "Minimiert Event-Friction: Heimspiele möglichst nicht an Tagen "
            "mit Großevents (Marathons, Konzerte, Stadtfeste). "
            "Lokale Behörden und Fan-Erlebnis priorisiert."
        ),
        w_travel=0.5, w_revenue=-2e-7, w_fatigue=10.0,
        w_away_streak=2000.0, w_off_day=10_000_000.0,
        w_tv=-100.0, w_friction=5000.0,
    ),
}


def get_pareto(profile_name: str) -> ParetoProfile:
    """Gibt ein benanntes Pareto-Profil zurück."""
    if profile_name not in PARETO_PROFILES:
        raise KeyError(
            f"Unbekanntes Pareto-Profil '{profile_name}'. "
            f"Verfügbar: {list(PARETO_PROFILES.keys())}"
        )
    return PARETO_PROFILES[profile_name]


def list_pareto_profiles() -> list:
    """Gibt alle Pareto-Profile als Liste von Dicts zurück."""
    return [p.to_dict() for p in PARETO_PROFILES.values()]
