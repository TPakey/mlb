"""CO₂-Modell für die Saison-Reisedistanz (Sprint 3, Track C1).

Wandelt geflogene Charter-Kilometer in CO₂-Emissionen um. MLB-Teams reisen per
**Team-Charter** (ein Flugzeug pro Trip, kein Linienflug-Sharing), daher rechnen
wir auf **Flugzeug-Ebene** (kg CO₂ pro Flugzeug-km), nicht pro Passagier.

Methodik (zwei zitierte Faktoren, multipliziert):

1. **Treibstoff → CO₂:** 3,16 kg CO₂ je kg verbranntem Jet-A.
   ICAO CAEP-Standardfaktor (ICAO Doc 9889; identisch in CORSIA, EU ETS, ISO).
   Quelle: ICAO / EUROCONTROL Standard Inputs ("3.16 kg CO2 from 1 kg jet fuel").

2. **Verbrauch je km:** 3,98 kg Treibstoff je Flugzeug-km für eine repräsentative
   Narrowbody (Boeing 737-800) — der typische MLB-Team-Charter-Typ.
   Quelle: Wikipedia "Fuel economy in aircraft" (737-800: 3,98 kg/km).

Daraus: **CO₂_FAKTOR = 3,16 × 3,98 = 12,58 kg CO₂ je Flugzeug-km.**

Belege + Diskussion: docs/SUSTAINABILITY_RESEARCH.md.

Die Faktoren sind als Modul-Konstanten gepflegt und können bei besserer Datenlage
(z.B. flottenspezifischer Mix aus 737/757/A321, Frachtzuschlag für Equipment)
zentral aktualisiert werden — bewusst eine *dokumentierte Annahme*, kein
erfundener Wert.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from .travel import SeasonTravelReport

# ---- Zitierte Faktoren (siehe Modul-Docstring + docs/SUSTAINABILITY_RESEARCH.md) ----

#: kg CO₂ je kg verbranntem Jet-A — ICAO CAEP (Doc 9889), CORSIA, EU ETS.
JET_A_CO2_PER_KG_FUEL: float = 3.16

#: kg Treibstoff je Flugzeug-km — Boeing 737-800 (repräsentativer Team-Charter).
CHARTER_FUEL_BURN_KG_PER_KM: float = 3.98

#: Abgeleitet: kg CO₂ je Flugzeug-km.
CO2_KG_PER_KM: float = JET_A_CO2_PER_KG_FUEL * CHARTER_FUEL_BURN_KG_PER_KM  # ≈ 12.58


def co2_kg_from_km(km: float) -> float:
    """CO₂ in Kilogramm für eine gegebene Flugdistanz (Flugzeug-Charter)."""
    return km * CO2_KG_PER_KM


def co2_tonnes_from_km(km: float) -> float:
    """CO₂ in metrischen Tonnen für eine gegebene Flugdistanz."""
    return co2_kg_from_km(km) / 1000.0


@dataclass(frozen=True)
class Co2Report:
    """CO₂-Bilanz einer Saison, abgeleitet aus den Reise-km."""
    total_tonnes: float
    per_team_tonnes: Dict[str, float] = field(default_factory=dict)
    kg_per_km_factor: float = CO2_KG_PER_KM

    @property
    def avg_tonnes_per_team(self) -> float:
        return self.total_tonnes / max(1, len(self.per_team_tonnes))


def compute_co2_report(travel: SeasonTravelReport) -> Co2Report:
    """Berechnet die CO₂-Bilanz aus einem SeasonTravelReport (Pro-Team-km)."""
    per_team = {
        tid: co2_tonnes_from_km(log.total_km)
        for tid, log in travel.by_team.items()
    }
    total = co2_tonnes_from_km(travel.total_km)
    return Co2Report(total_tonnes=total, per_team_tonnes=per_team)
