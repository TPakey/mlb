"""Penalty-Registry — benannte, transparent gewichtete Strafen.

Der Optimizer "lernt", was Spielplan-Qualität verletzt, indem er Penalties
aufsummiert. Aus dem Forschungspapier ("Penalty systems encode league values"):
was hier hoch bestraft ist, ist das, was die Liga wirklich wertschätzt.

Jede Penalty hat:
- code  → eindeutige ID
- name  → menschenlesbar
- base  → Basis-Strafwert (in km-Equivalent)
- desc  → Erklärung
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class Penalty:
    code: str
    name: str
    base: float
    category: str
    desc: str


REGISTRY: Dict[str, Penalty] = {
    # ---- Travel ----
    "TRV_EAST_OVERNIGHT": Penalty(
        "TRV_EAST_OVERNIGHT", "Westkueste→Ostkueste Übernachtflug",
        180.0, "travel",
        "Spielt eine Mannschaft abends im Westen und am nächsten Tag früh im Osten, "
        "ist das einer der härtesten Belastungsmuster.",
    ),
    "TRV_FOURTH_TZ_8DAYS": Penalty(
        "TRV_FOURTH_TZ_8DAYS", "4. Zeitzonen-Hop in 8 Tagen",
        250.0, "travel",
        "Mehrere Zeitzonen-Wechsel in kurzer Folge → kumulative Müdigkeit.",
    ),
    "TRV_CROSS_COUNTRY_TURNAROUND": Penalty(
        "TRV_CROSS_COUNTRY_TURNAROUND", "Cross-Country mit <24h Pause",
        400.0, "travel",
        ">3000 km Flug ohne Erholungstag dazwischen.",
    ),

    # ---- Fatigue ----
    "FAT_14_CONSEC_GAMES": Penalty(
        "FAT_14_CONSEC_GAMES", "14+ Spiele in Serie ohne Off-Day",
        200.0, "fatigue",
        "Bullpen-Stress, Verletzungsrisiko, Recovery-Lücke.",
    ),
    "FAT_LATE_ARRIVAL_RUN": Penalty(
        "FAT_LATE_ARRIVAL_RUN", "3 späte Ankünfte in 5 Tagen",
        150.0, "fatigue",
        "Schlaf-Defizit akkumuliert.",
    ),
    "FAT_COMPRESSED_SCHEDULE": Penalty(
        "FAT_COMPRESSED_SCHEDULE", "Verdichteter Spielplan (Doubleheader nach Reisetag)",
        300.0, "fatigue",
        "Direkt nach Übernacht-Reise — sehr hohe Belastung.",
    ),

    # ---- Fairness ----
    "FAIR_REST_DELTA_4PLUS": Penalty(
        "FAIR_REST_DELTA_4PLUS", "Rest-Differenz >4 Tage zwischen Gegnern",
        250.0, "fairness",
        "Ein Team hat 4+ Ruhetage Vorsprung — sportliche Fairness verletzt.",
    ),
    "FAIR_ELITE_OPP_CLUSTER": Penalty(
        "FAIR_ELITE_OPP_CLUSTER", "Elite-Gegner-Cluster ungleichmässig verteilt",
        100.0, "fairness",
        "Ein Team bekommt mehrere Top-Gegner direkt hintereinander.",
    ),

    # ---- Broadcast / Revenue ----
    "BCAST_RIVALRY_HIDDEN": Penalty(
        "BCAST_RIVALRY_HIDDEN", "Top-Rivalität ausserhalb Primetime",
        500.0, "broadcast",
        "Marquee-Matchup (z. B. NYY-BOS) in einem Slot ohne nationale TV-Reichweite.",
    ),
    "BCAST_HOLIDAY_NO_MARQUEE": Penalty(
        "BCAST_HOLIDAY_NO_MARQUEE", "Feiertag ohne hochwertiges Matchup",
        300.0, "broadcast",
        "Memorial Day / 4. Juli / Labor Day brauchen attraktive Spiele.",
    ),
    "REV_WEEKEND_LOW_DEMAND": Penalty(
        "REV_WEEKEND_LOW_DEMAND", "Schwacher Gegner an Top-Wochenende",
        150.0, "revenue",
        "Begrenzte Wochenend-Slots an hochzahlende Märkte verschwendet.",
    ),

    # ---- Weather / Operations ----
    "WX_COLD_OPEN_APRIL": Penalty(
        "WX_COLD_OPEN_APRIL", "Heimserie in Kaltstadt im April (offenes Dach)",
        120.0, "weather",
        "Schnee-/Frostrisiko; schlechte Spielqualität, Verletzungsrisiko.",
    ),
    "WX_HEAT_DAY_GAME": Penalty(
        "WX_HEAT_DAY_GAME", "Tagspiel in Hitzestadt im Hochsommer",
        80.0, "weather",
        "Spielergesundheit und Fan-Komfort.",
    ),
    "WX_HURRICANE_WINDOW": Penalty(
        "WX_HURRICANE_WINDOW", "Heimserie im Hurricane-Risikofenster",
        180.0, "weather",
        "Wettervorbehalt, Reise-/Stadion-Risiko.",
    ),

    # ---- Resilience ----
    "RES_NO_REPAIR_PATH": Penalty(
        "RES_NO_REPAIR_PATH", "Keine einfache Wiederholungs-Option bei Ausfall",
        200.0, "resilience",
        "Verschobenes Spiel wäre nur mit Doubleheader-Stress nachholbar.",
    ),
}


def get(code: str) -> Penalty:
    if code not in REGISTRY:
        raise KeyError(f"Unbekannter Penalty-Code: {code}")
    return REGISTRY[code]


def by_category() -> Dict[str, list]:
    out: Dict[str, list] = {}
    for p in REGISTRY.values():
        out.setdefault(p.category, []).append(p)
    return out
