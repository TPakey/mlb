"""HAP-Pattern-Datenstruktur (Sprint 2.3a; A20-Subpackage-Split).

Implementierungsmodul des `colgen`-Subpackages. Oeffentlich re-exportiert ueber
`src.column_generation` (Importpfade bleiben stabil).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from ..two_phase_pacing import TeamPacing


@dataclass(frozen=True)
class Pattern:
    """Ein Home-Away-Pattern fuer ein Team.

    Pro Tag eine von drei Markierungen: 'H' (Heim), 'A' (Auswaerts), 'O' (Off).
    Die Pattern-Laenge ist `total_days`.
    """
    team_id: str
    marks: Tuple[str, ...]   # 'H' / 'A' / 'O' pro Tag-Index

    def __post_init__(self):
        for m in self.marks:
            if m not in ('H', 'A', 'O'):
                raise ValueError(f"Ungueltige Mark: {m!r}")

    @property
    def n_home(self) -> int:
        return sum(1 for m in self.marks if m == 'H')

    @property
    def n_away(self) -> int:
        return sum(1 for m in self.marks if m == 'A')

    @property
    def n_off(self) -> int:
        return sum(1 for m in self.marks if m == 'O')

    def is_home_at(self, d: int) -> bool:
        return self.marks[d] == 'H'

    def is_away_at(self, d: int) -> bool:
        return self.marks[d] == 'A'

    def signature(self) -> str:
        """Eindeutiger Identifier (fuer Dedup)."""
        return "".join(self.marks)


def pacing_to_pattern(pacing: TeamPacing, total_days: int) -> Pattern:
    """Konvertiert ein Phase-A-Output zu einem Pattern."""
    marks = ['O'] * total_days
    for day, is_home in pacing.schedule:
        marks[day] = 'H' if is_home else 'A'
    return Pattern(team_id=pacing.team_id, marks=tuple(marks))

