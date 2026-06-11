"""Datenquellen-Adapter für externe Schedule-Provider.

Drei Implementierungen geplant:
- `sportsdata_io.SportsDataIoAdapter`   — kommerziell, mit API-Key
- `mlb_statsapi.MlbStatsApiAdapter`     — freie MLB Stats API
- `local_file.LocalFileAdapter`         — JSON/CSV aus dem Filesystem

Architektur-Idee: das restliche System spricht NUR mit dem Adapter-Interface,
nicht mit konkreten Quellen. Wenn MLB das Produkt kauft und ihre interne
Datenquelle einbindet, schreibt man einen vierten Adapter und konfiguriert ihn.
"""
from .base import DataSourceAdapter, DataSourceError
from .local_file import LocalFileAdapter
from .sportsdata_io import SportsDataIoAdapter

__all__ = [
    "DataSourceAdapter",
    "DataSourceError",
    "LocalFileAdapter",
    "SportsDataIoAdapter",
]
