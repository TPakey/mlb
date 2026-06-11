"""Konfiguration und Secrets — liest .env-Datei und exponiert sie typisiert.

Keine externe Abhängigkeit; minimaler eigener .env-Parser.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"


def _load_env_file(path: Path) -> None:
    """Sehr simpler .env-Loader. Liest KEY=VALUE-Zeilen, ignoriert Kommentare.

    Audit A8 (Sprint A-4): Bewusst minimalistisch. Erlaubte Syntax:
      - `KEY=value`            (kein Whitespace um =)
      - `KEY=value with spaces`
      - `# Kommentar`          (ganze Zeile)
      - `KEY="quoted"` oder `KEY='quoted'`
    NICHT unterstützt: Multi-Line-Werte, Escape-Sequenzen, Variablen-
    Substitution. Wer Komplexeres braucht, soll `python-dotenv` als optionale
    Dependency einziehen — dieser Loader ist nur für den einen API-Key gedacht.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Nicht überschreiben, falls schon im Environment gesetzt
        os.environ.setdefault(key, value)


_load_env_file(ENV_FILE)


def get_sportsdataio_key() -> Optional[str]:
    return os.environ.get("SPORTSDATAIO_MLB_KEY") or None


def get_gurobi_wls() -> Optional[dict]:
    """Gurobi Web-License-Service-Credentials aus .env, falls vollständig gesetzt.

    Erwartet (Sprint 5.4): ``GRB_WLSACCESSID``, ``GRB_WLSSECRET``, ``GRB_LICENSEID``.
    Jonas muss nur diese drei in .env einfügen → der green-field Gurobi-Solver
    nutzt sie automatisch (kein Code-Eingriff). Gibt None zurück, wenn unvollständig.
    """
    accessid = os.environ.get("GRB_WLSACCESSID", "").strip()
    secret = os.environ.get("GRB_WLSSECRET", "").strip()
    licid = os.environ.get("GRB_LICENSEID", "").strip()
    if accessid and secret and licid:
        return {"WLSACCESSID": accessid, "WLSSECRET": secret,
                "LICENSEID": int(licid) if licid.isdigit() else licid}
    return None


def get_gurobi_license_file() -> Optional[str]:
    """Pfad zu einer ``gurobi.lic`` (Named-User/Academic), falls per
    ``GRB_LICENSE_FILE`` gesetzt. Gurobi findet eine Datei im Default-Pfad auch
    ohne diese Variable."""
    return os.environ.get("GRB_LICENSE_FILE") or None


def require_sportsdataio_key() -> str:
    key = get_sportsdataio_key()
    if not key:
        raise RuntimeError(
            "SPORTSDATAIO_MLB_KEY fehlt. Bitte in .env eintragen "
            f"(Datei: {ENV_FILE})."
        )
    return key
