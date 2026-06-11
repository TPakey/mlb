"""Legacy: TradeoffProfile (Sprint 0/1, 7-Dimensionen).

Altbestand des Prototype-Scoring-Systems. Wird nur noch vom Legacy-Pfad
(`legacy/optimizer.py`, `legacy/ai_explainer.py`) genutzt. Der aktive Hauptpfad
verwendet `src/profiles.py::ParetoProfile`. Siehe docs/ARCHITECTURE_DECISION.md.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict


@dataclass(frozen=True)
class TradeoffProfile:
    name: str
    description: str
    w_travel: float
    w_fatigue: float
    w_fairness: float
    w_broadcast: float
    w_revenue: float
    w_weather: float
    w_resilience: float

    def to_dict(self) -> dict:
        return asdict(self)


PROFILES: Dict[str, TradeoffProfile] = {
    "balanced": TradeoffProfile(
        name="Balanced",
        description="Gleichgewichteter Trade-off: keine Dimension dominiert. "
                    "Sinnvolle Default-Wahl, wenn keine politische Vorgabe existiert.",
        w_travel=1.0, w_fatigue=1.0, w_fairness=1.0,
        w_broadcast=1.0, w_revenue=1.0, w_weather=1.0, w_resilience=1.0,
    ),
    "player_health": TradeoffProfile(
        name="Player Health",
        description="Spielergesundheit und Erholung haben Vorrang. "
                    "Reduziert Müdigkeit, Reisedichte und Wetter-Belastung.",
        w_travel=1.5, w_fatigue=3.0, w_fairness=1.2,
        w_broadcast=0.6, w_revenue=0.6, w_weather=2.0, w_resilience=1.5,
    ),
    "revenue_max": TradeoffProfile(
        name="Revenue Max",
        description="TV-Slots und Attendance werden maximiert. "
                    "Travel und Fatigue treten in den Hintergrund.",
        w_travel=0.5, w_fatigue=0.5, w_fairness=0.7,
        w_broadcast=2.5, w_revenue=2.5, w_weather=0.8, w_resilience=0.8,
    ),
    "fan_first": TradeoffProfile(
        name="Fan-First",
        description="Wochenend-Zugänglichkeit, lokale Sichtbarkeit, "
                    "Rivalitäts-Inszenierung. Travel weniger relevant.",
        w_travel=0.7, w_fatigue=0.8, w_fairness=1.0,
        w_broadcast=2.0, w_revenue=1.5, w_weather=1.0, w_resilience=0.8,
    ),
    "sustainability": TradeoffProfile(
        name="Sustainability",
        description="CO₂-Fussabdruck und Routing-Effizienz priorisiert. "
                    "Maximale Travel-Reduktion.",
        w_travel=3.0, w_fatigue=1.2, w_fairness=1.0,
        w_broadcast=0.7, w_revenue=0.7, w_weather=1.0, w_resilience=1.0,
    ),
    "fairness": TradeoffProfile(
        name="Fairness",
        description="Varianz zwischen Teams (Travel, Ruhetage, TV) minimiert. "
                    "Keine systematischen Nachteile.",
        w_travel=1.2, w_fatigue=1.5, w_fairness=3.0,
        w_broadcast=0.9, w_revenue=0.9, w_weather=1.0, w_resilience=1.2,
    ),
}


def get(profile_name: str) -> TradeoffProfile:
    if profile_name not in PROFILES:
        raise KeyError(
            f"Unbekanntes Profil '{profile_name}'. Verfügbar: {list(PROFILES.keys())}"
        )
    return PROFILES[profile_name]


def list_profiles() -> list:
    return [p.to_dict() for p in PROFILES.values()]
