"""Gurobi-Lizenz einrichten — ein Kommando, klare Diagnose (Runde 3).

AUF DEM ENTWICKLER-RECHNER ausführen (NICHT in einer Sandbox/Container-Session:
ein ``grbgetkey``-Code ist EINMALIG verwendbar und bindet die Lizenz an die
Maschine, auf der er eingelöst wird — in einem Wegwerf-Container wäre er
verbrannt; Named-User-Academic-Codes brauchen zudem das Uni-Netz):

    # Status + Anleitung:
    python -m tools.setup_gurobi

    # Named-User-/Academic-Code einlösen (ruft grbgetkey auf, schreibt .env):
    python -m tools.setup_gurobi --key 5761e08e-xxxx-xxxx-xxxx-xxxxxxxxxxxx

    # Alternativ WLS-Credentials (laufen auch in Containern/Cloud):
    python -m tools.setup_gurobi --wls ACCESSID SECRET LICENSEID

    # Nur validieren (loest ein Modell oberhalb des Restricted-Limits):
    python -m tools.setup_gurobi --validate

Lizenzwege:
- **Named-User (grbgetkey):** braucht das volle Gurobi-Paket (enthaelt das
  ``grbgetkey``-Binary; pip-gurobipy enthaelt es NICHT) ODER man fuehrt
  grbgetkey einmalig manuell aus. Ergebnis ist eine ``gurobi.lic`` →
  dieses Tool traegt ``GRB_LICENSE_FILE`` in ``.env`` ein.
- **WLS (Web License Service):** portal.gurobi.com → Licenses → Academic WLS.
  Drei Werte, maschinenunabhaengig, container-tauglich → ``.env``.
src/config laedt beide Wege automatisch (get_gurobi_wls/get_gurobi_license_file).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"

# uebliche Ablageorte einer gurobi.lic nach grbgetkey
LIC_CANDIDATES = [
    Path.home() / "gurobi.lic",
    Path("/Library/gurobi/gurobi.lic"),          # macOS
    Path("/opt/gurobi/gurobi.lic"),              # Linux
    Path("C:/gurobi/gurobi.lic"),                # Windows
]


def _write_env(updates: dict) -> None:
    """Schreibt/aktualisiert Schluessel in .env (bestehende Eintraege bleiben)."""
    lines: list = []
    seen: set = set()
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            key = line.split("=", 1)[0].strip() if "=" in line else None
            if key in updates:
                lines.append(f"{key}={updates[key]}")
                seen.add(key)
            else:
                lines.append(line)
    for k, v in updates.items():
        if k not in seen:
            lines.append(f"{k}={v}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  .env aktualisiert: {', '.join(updates)}  ({ENV_FILE})")


def status() -> dict:
    sys.path.insert(0, str(REPO_ROOT))
    from src.greenfield_gurobi import gurobi_status
    st = gurobi_status()
    print(f"Status: {st}")
    return st


def validate() -> bool:
    """Beweist Voll-Lizenz durch ein Modell OBERHALB des Restricted-Limits
    (Restricted: ~2000 Variablen/Constraints). Messen statt behaupten."""
    try:
        import gurobipy as gp
    except ImportError:
        print("gurobipy fehlt: pip install gurobipy")
        return False
    sys.path.insert(0, str(REPO_ROOT))
    from src.greenfield_gurobi import _make_env
    n = 3000   # > Restricted-Limit
    try:
        env = _make_env(verbose=False)
        m = gp.Model("license_probe", env=env)
        x = m.addVars(n, ub=1.0)
        m.addConstrs((x[i] + x[(i + 1) % n] <= 1.5 for i in range(n)))
        m.setObjective(x.sum(), gp.GRB.MAXIMIZE)
        m.optimize()
        ok = m.Status == gp.GRB.OPTIMAL
        m.dispose(); env.dispose()
        print(f"VOLL-LIZENZ BESTAETIGT ✓ — Probe-Modell mit {n} Variablen "
              f"geloest (Restricted-Limit liegt darunter).")
        return ok
    except Exception as exc:
        if "size-limited" in str(exc) or "Model too large" in str(exc):
            print("RESTRICTED LICENSE — Probe-Modell über dem Größenlimit "
                  "abgelehnt. Lizenz noch nicht aktiv. → --key oder --wls.")
        else:
            print(f"Validierung fehlgeschlagen: {exc}")
        return False


def setup_key(code: str) -> int:
    """grbgetkey ausfuehren (falls vorhanden) und GRB_LICENSE_FILE setzen."""
    if os.environ.get("CONTAINER") or Path("/.dockerenv").exists():
        print("ABBRUCH: Das sieht nach einem Container aus. Der Code ist "
              "EINMALIG und maschinengebunden — auf dem echten Rechner im "
              "Uni-Netz ausfuehren.")
        return 1
    grbgetkey = shutil.which("grbgetkey")
    if grbgetkey is None:
        print("grbgetkey nicht im PATH (pip-gurobipy enthaelt es nicht).")
        print("Option A: Voll-Paket laden (gurobi.com/downloads), dann erneut.")
        print("Option B: grbgetkey manuell ausfuehren; danach:")
        print("          python -m tools.setup_gurobi --license-file ~/gurobi.lic")
        return 1
    print(f"Fuehre aus: grbgetkey {code}   (Uni-Netz/VPN erforderlich)")
    proc = subprocess.run([grbgetkey, code], capture_output=True, text=True)
    sys.stdout.write(proc.stdout or "")
    sys.stderr.write(proc.stderr or "")
    if proc.returncode != 0:
        out = (proc.stdout or "") + (proc.stderr or "")
        if "303" in out or "academic domain" in out:
            print("\n→ URSACHE: Du bist NICHT im Uni-Netz (ERROR 303). Der Code "
                  "bleibt gueltig — im Uni-WLAN oder per Uni-VPN (eduVPN/"
                  "AnyConnect) einfach erneut ausfuehren.")
        else:
            print(f"\ngrbgetkey Exit {proc.returncode} — Lizenz nicht erstellt.")
        return proc.returncode
    lic = next((p for p in LIC_CANDIDATES if p.exists()), None)
    if lic is None:
        print("gurobi.lic nicht an Standardorten gefunden — Pfad manuell setzen:")
        print("  python -m tools.setup_gurobi --license-file /pfad/zu/gurobi.lic")
        return 1
    _write_env({"GRB_LICENSE_FILE": str(lic)})
    return 0 if validate() else 1


def main() -> int:
    p = argparse.ArgumentParser(description="Gurobi-Lizenz einrichten/validieren")
    p.add_argument("--key", help="Named-User-Aktivierungscode (grbgetkey ...)")
    p.add_argument("--wls", nargs=3, metavar=("ACCESSID", "SECRET", "LICENSEID"),
                   help="WLS-Credentials (portal.gurobi.com → Academic WLS)")
    p.add_argument("--license-file", help="Pfad zu vorhandener gurobi.lic")
    p.add_argument("--validate", action="store_true", help="nur validieren")
    args = p.parse_args()

    if args.wls:
        _write_env({"GRB_WLSACCESSID": args.wls[0],
                    "GRB_WLSSECRET": args.wls[1],
                    "GRB_LICENSEID": args.wls[2]})
        return 0 if validate() else 1
    if args.license_file:
        lic = Path(args.license_file).expanduser()
        if not lic.exists():
            print(f"Datei nicht gefunden: {lic}")
            return 1
        _write_env({"GRB_LICENSE_FILE": str(lic)})
        return 0 if validate() else 1
    if args.key:
        return setup_key(args.key)
    if args.validate:
        return 0 if validate() else 1

    # Default: Status + Anleitung
    st = status()
    if st.get("license_source") not in (None, "Default/Restricted"):
        print("Lizenz konfiguriert. Voll-Beweis: python -m tools.setup_gurobi --validate")
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
