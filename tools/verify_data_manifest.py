"""Daten-Manifest pruefen/erneuern (Review-Runde 2, Punkt 8).

SHA256-Freeze gegen stillen Datendrift der Kern-Datendateien (Schedules,
Stammdaten, Appendix C). Der LocalFileAdapter prueft beim Laden automatisch
(Warnung); dieses Tool macht die Pruefung explizit bzw. erneuert das Manifest
nach einem BEWUSSTEN Daten-Update.

    python -m tools.verify_data_manifest            # pruefen (Exit 1 bei Drift)
    python -m tools.verify_data_manifest --update   # Manifest neu schreiben
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
MANIFEST = DATA_DIR / "MANIFEST.sha256.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify() -> int:
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    bad = 0
    for name, expected in man["files"].items():
        p = DATA_DIR / name
        if not p.exists():
            print(f"FEHLT: {name}")
            bad += 1
            continue
        actual = sha256(p)
        ok = actual == expected
        print(f"{'OK  ' if ok else 'DRIFT'} {name}"
              + ("" if ok else f"  erwartet {expected[:16]}…, ist {actual[:16]}…"))
        if not ok:
            bad += 1
    return 1 if bad else 0


def update() -> int:
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for name in man["files"]:
        man["files"][name] = sha256(DATA_DIR / name)
    MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(f"Manifest erneuert: {MANIFEST}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Daten-Manifest pruefen/erneuern")
    p.add_argument("--update", action="store_true",
                   help="Manifest nach bewusstem Daten-Update neu schreiben")
    args = p.parse_args()
    return update() if args.update else verify()


if __name__ == "__main__":
    sys.exit(main())
