"""Timezone-Konstanten und DST-aware Offset-Berechnung (Audit A15, Sprint A-3).

Eigenständiges Modul, um den Zirkel `data_loader.Team` ↔ `distance.TIMEZONE_OFFSET`
zu vermeiden. Beide importierten zuvor übereinander herum, was durch einen
Lazy-Import in `_validate_teams` halb-stabil aufgelöst war; mit dem Auszug
hierher ist die Abhängigkeit sauber linear.

Importiert von: `data_loader.py` (für die Timezone-Validierung) und
`distance.py` (für die Reise-Hop-Berechnung).
"""
from __future__ import annotations

import warnings
from datetime import date, datetime
from typing import Optional

try:
    from zoneinfo import ZoneInfo
    # Audit A4 (Sprint A-1): Probe-Zone laden, damit ein fehlendes `tzdata`
    # NICHT still durchgeht — gerade auf Alpine/Minimal-Containern.
    ZoneInfo("America/New_York")
    _HAS_ZONEINFO = True
    # Audit A14 (Sprint A-4): tzdata-Version festhalten fuer Reproduzierbarkeits-
    # Reports. Auf modernen Linux-Systemen liegt sie i.d.R. unter /usr/share/zoneinfo,
    # in Python-Distributions ueber das `tzdata`-Package.
    try:
        import importlib.metadata as _md
        TZDATA_VERSION = _md.version("tzdata")
    except Exception:
        TZDATA_VERSION = "system"   # vermutlich OS-tzdata, keine Python-Version verfuegbar
except Exception as _zi_exc:  # pragma: no cover
    import warnings as _warnings
    _warnings.warn(
        f"zoneinfo/tzdata nicht verfügbar ({_zi_exc!r}). DST-Korrektur in "
        f"tz_offset_hours() ist DEAKTIVIERT — Reise-km für DST-aktive "
        f"Zeitzonen sind dann mit Standard-Time-Offsets berechnet (vor allem "
        f"ARI-Routings im Sommer betroffen). `pip install tzdata` behebt das.",
        RuntimeWarning,
        stacklevel=2,
    )
    _HAS_ZONEINFO = False
    TZDATA_VERSION = "n/a"


# Statische Standard-Time-Offsets (Fallback, falls zoneinfo nicht verfügbar
# oder kein Datum bekannt). DST wird hier NICHT berücksichtigt.
TIMEZONE_OFFSET = {
    "America/New_York": -5,
    "America/Toronto": -5,
    "America/Chicago": -6,
    "America/Denver": -7,
    "America/Phoenix": -7,
    "America/Los_Angeles": -8,
}


def tz_offset_hours(tz_name: str, on_date: Optional[date] = None) -> int:
    """UTC-Offset einer Zeitzone in Stunden — DST-korrekt (M2, Sprint 2.11).

    Mit `on_date` und verfügbarem `zoneinfo` wird der *effektive* Offset zum
    konkreten Datum berechnet (z.B. America/New_York = -4 im Sommer, -5 im
    Winter; America/Phoenix ganzjährig -7, da kein DST). Ohne Datum oder ohne
    zoneinfo fällt die Funktion auf die statischen Standard-Time-Offsets zurück.
    """
    if on_date is not None and _HAS_ZONEINFO:
        try:
            dt = datetime(on_date.year, on_date.month, on_date.day, 12,
                          tzinfo=ZoneInfo(tz_name))
            off = dt.utcoffset()
            if off is not None:
                return round(off.total_seconds() / 3600.0)
        except Exception:
            pass
    # Defensive: unbekannte/neue Zeitzone soll keinen KeyError werfen, sondern
    # mit einer Warnung auf Offset 0 (UTC) zurueckfallen.
    off = TIMEZONE_OFFSET.get(tz_name)
    if off is None:
        warnings.warn(
            f"Unbekannte Zeitzone {tz_name!r} ohne Standard-Offset — "
            f"fallback auf 0 (UTC). Bitte in TIMEZONE_OFFSET ergaenzen.",
            RuntimeWarning,
            stacklevel=2,
        )
        return 0
    return off
