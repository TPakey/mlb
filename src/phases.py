"""Saison-Phasen — zeitfenster-basierte Gewichtung der Zielfunktion (Sprint 3).

Das Kern-Produktmerkmal fuer MLB Season Schedulers: Statt einer einzigen globalen
Gewichtung ueber die ganze Saison definiert der Scheduler **Phasen** (Zeitfenster)
mit eigenen Prioritaeten. Beispiele:

- **Saisonstart / -ende** (mehr Zuschauer): TV + Revenue hochgewichten — der
  Optimizer nimmt dort bewusst mehr Reise in Kauf, um Marquee-Spiele an
  Premium-Tagen zu platzieren.
- **Belastungs-Phase** (z. B. lange Hitze-Woche, dichtes Programm): Fatigue/Reise
  staerker gewichten, TV/Revenue vernachlaessigen.

Mechanik: Jede Phase hat ein Datumsfenster und **Multiplikatoren** je Zieldimension.
Fuer ein Spiel an Datum d wird der effektive Beitrag jeder Dimension mit dem Produkt
der Multiplikatoren aller das Datum abdeckenden Phasen skaliert (Default 1.0 = keine
Aenderung). Die Optimierung (`optimize_pareto(..., phase_plan=...)`) minimiert dann
die phasen-gewichtete Energie; der berichtete ParetoBundle bleibt unveraendert die
*tatsaechlichen* Werte (wir gewichten, was PRIORISIERT wird — nicht, was gemessen wird).

V1 deckt die pro-Spiel-lokalisierbaren Ziele ab: **revenue, tv, friction**. Damit ist
das Haupt-Szenario (TV/Revenue je Fenster hoch/runter, Reise implizit ent-/gewichtet)
vollstaendig bedienbar. Travel/Fatigue als eigene Phasen-Hebel sind der naechste
Ausbau (siehe docs).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List

# Phasen-gewichtbare Zieldimensionen (V1: pro-Spiel lokalisierbar).
PHASE_KEYS = ("revenue", "tv", "friction")


@dataclass(frozen=True)
class SchedulePhase:
    """Ein benanntes Zeitfenster mit Gewichts-Multiplikatoren je Zieldimension.

    multipliers: z. B. {"tv": 3.0, "revenue": 2.0} — in diesem Fenster zaehlen
    TV-Score 3x und Revenue 2x so stark fuer die Optimierung. Fehlende Keys = 1.0.
    """
    name: str
    start: date
    end: date                       # inklusiv
    multipliers: Dict[str, float] = field(default_factory=dict)

    def covers(self, d: date) -> bool:
        return self.start <= d <= self.end

    def mult_for(self, key: str) -> float:
        return float(self.multipliers.get(key, 1.0))


@dataclass
class PhasePlan:
    """Sammlung von Phasen. Multiplikatoren ueberlappender Phasen multiplizieren sich."""
    phases: List[SchedulePhase] = field(default_factory=list)

    def multiplier(self, d: date, key: str) -> float:
        """Effektiver Multiplikator fuer Dimension `key` am Datum `d`
        (Produkt aller abdeckenden Phasen; 1.0 wenn keine zutrifft)."""
        m = 1.0
        for p in self.phases:
            if p.covers(d):
                m *= p.mult_for(key)
        return m

    def is_empty(self) -> bool:
        return not self.phases

    # ---- Persistenz (Scheduler-editierbar) ----

    def to_dict(self) -> dict:
        return {
            "phases": [
                {
                    "name": p.name,
                    "start": p.start.isoformat(),
                    "end": p.end.isoformat(),
                    "multipliers": dict(p.multipliers),
                }
                for p in self.phases
            ]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PhasePlan":
        phases = []
        for p in data.get("phases", []):
            mult = {k: float(v) for k, v in (p.get("multipliers") or {}).items()}
            unknown = set(mult) - set(PHASE_KEYS)
            if unknown:
                raise ValueError(
                    f"Phase '{p.get('name')}': unbekannte Dimension(en) {sorted(unknown)}. "
                    f"Erlaubt (V1): {list(PHASE_KEYS)}."
                )
            phases.append(SchedulePhase(
                name=p.get("name", "phase"),
                start=date.fromisoformat(p["start"]),
                end=date.fromisoformat(p["end"]),
                multipliers=mult,
            ))
        return cls(phases=phases)

    @classmethod
    def load(cls, path: Path) -> "PhasePlan":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
