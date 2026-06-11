"""Abstraktes Adapter-Interface für Schedule-Datenquellen."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from ..season import Season


class DataSourceError(Exception):
    """Wird ausgelöst, wenn eine Datenquelle Daten nicht laden kann."""


class DataSourceAdapter(ABC):
    """Minimal-Interface, das jede Datenquelle anbieten muss.

    Aktuell brauchen wir nur Schedule-Daten — Erweiterungen (Stats, Injuries,
    Lines) können später hinzukommen.
    """

    #: Klar lesbarer Name der Quelle für Logs und Reports
    name: str = "abstract"

    @abstractmethod
    def fetch_season_schedule(
        self,
        season: int,
        game_type: str = "R",
    ) -> Season:
        """Liefert den vollständigen Saisonkalender als `Season`-Objekt.

        Args:
            season: Vierstelliges Saisonjahr (z. B. 2024).
            game_type: Spieltyp-Filter. "R" = Regular Season.
        """
        raise NotImplementedError

    def available_seasons(self) -> Optional[List[int]]:
        """Optional: welche Saisons unterstützt der Adapter? None = unbekannt."""
        return None
