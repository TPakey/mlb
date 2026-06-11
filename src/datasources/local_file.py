"""Adapter, der Schedule-Daten aus lokalen JSON-Dateien lädt.

Unterstützt aktuell:
- MLB-Stats-API-Format (statsapi.mlb.com JSON-Antworten)
- SportsDataIO-Format (Games-Endpoint JSON)
"""
from __future__ import annotations

import json
from pathlib import Path

from ..season import Season
from ..loaders import load_mlb_schedule_json
from .base import DataSourceAdapter, DataSourceError


class LocalFileAdapter(DataSourceAdapter):
    """Lädt Saisonkalender aus einer JSON-Datei im Filesystem.

    Format wird automatisch erkannt: MLB-Stats-API oder SportsDataIO.
    """

    name = "local_file"

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)

    def fetch_season_schedule(self, season: int, game_type: str = "R") -> Season:
        # Suche nach passender Datei (mehrere Namensschemas erlaubt)
        candidates = [
            self.base_dir / f"mlb_schedule_{season}.json",
            self.base_dir / f"schedule_{season}.json",
            self.base_dir / f"sportsdataio_games_{season}.json",
            self.base_dir / f"games_{season}.json",
        ]
        path = next((p for p in candidates if p.exists()), None)
        if not path:
            raise DataSourceError(
                f"Keine Schedule-Datei für Saison {season} gefunden. "
                f"Erwartet eine von: {[c.name for c in candidates]} in {self.base_dir}"
            )
        self._check_manifest(path)
        return self._load_auto(path, season, game_type)

    # Pro Prozess nur einmal je Datei warnen (Loader wird in Tests oft gerufen).
    _manifest_warned: set = set()

    def _check_manifest(self, path: Path) -> None:
        """Review-Runde 2 (Punkt 8): SHA256-Freeze-Check gegen stillen Datendrift.

        Vergleicht die Datei gegen ``data/MANIFEST.sha256.json`` (falls vorhanden
        und die Datei dort gelistet ist). Abweichung → WARNUNG (kein Abbruch:
        bewusste Daten-Updates müssen möglich sein; danach Manifest erneuern via
        ``python -m tools.verify_data_manifest --update``). Opt-out:
        Umgebungsvariable ``MLB_SKIP_MANIFEST=1``."""
        import hashlib
        import logging
        import os
        if os.environ.get("MLB_SKIP_MANIFEST") == "1":
            return
        manifest = self.base_dir / "MANIFEST.sha256.json"
        if not manifest.exists() or path.name in self._manifest_warned:
            return
        try:
            man = json.loads(manifest.read_text(encoding="utf-8"))
            expected = man.get("files", {}).get(path.name)
            if expected is None:
                return
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                self._manifest_warned.add(path.name)
                logging.getLogger("mlb.datasources").warning(
                    "DATEN-DRIFT: %s weicht vom Freeze-Manifest ab "
                    "(erwartet %s…, ist %s…). Alle Messungen gegen diese Datei "
                    "sind nicht mehr mit dokumentierten Ergebnissen vergleichbar. "
                    "Bewusstes Update? → tools/verify_data_manifest --update",
                    path.name, expected[:16], actual[:16])
        except Exception:  # pragma: no cover — Manifest-Check darf nie crashen
            pass

    def _load_auto(self, path: Path, season: int, game_type: str) -> Season:
        # Härtung (Sprint 4): korruptes/leeres JSON in eine klare DataSourceError
        # übersetzen statt eines rohen JSONDecodeError, der die Quelle verschleiert.
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DataSourceError(
                f"Schedule-Datei {path} enthält kein gültiges JSON: {exc}"
            ) from exc
        # MLB Stats API hat ein "dates"-Top-Level
        if isinstance(raw, dict) and "dates" in raw:
            return load_mlb_schedule_json(path, season=season, game_type=game_type)
        # SportsDataIO liefert eine Liste von Game-Objekten
        if isinstance(raw, list):
            return self._load_sportsdataio_format(raw, season, game_type)
        raise DataSourceError(
            f"Unbekanntes JSON-Format in {path}. Top-Level-Typ: {type(raw).__name__}"
        )

    def _load_sportsdataio_format(self, games_raw: list, season: int, game_type: str) -> Season:
        # Importieren wir lokal, um Zyklen zu vermeiden
        from .sportsdata_io import games_from_sportsdataio_payload
        return games_from_sportsdataio_payload(games_raw, season=season)
