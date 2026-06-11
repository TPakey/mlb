#!/bin/bash
# ============================================================
#  MLB Logistics Optimizer — Externe Daten laden (Doppelklick)
#  Lädt: Retrosheet-Originalpläne 2024/2025/2026 (Goldquelle)
#        + nationale TV-Broadcast-Fakten 2024/2025
#  Danach: Kreuzvalidierung + Originalplan-Messung + Manifest.
#  Braucht nur das macOS-eigene python3 (keine pip-Pakete).
# ============================================================
set -u
cd "$(dirname "$0")" || exit 1

PY="$(command -v python3 || echo /usr/bin/python3)"
echo "Projektordner: $(pwd)"
echo "Python:        $PY ($($PY --version 2>&1))"
echo

export PYTHONPATH="$(pwd)"
"$PY" -m tools.update_external_data --all --years 2024 2025 2026
RC=$?

echo
if [ $RC -eq 0 ]; then
  echo "✅ FERTIG — Daten geladen, kreuzvalidiert, Manifest erneuert."
  echo "   Sag Claude Bescheid (oder kopiere den Output oben in den Chat),"
  echo "   dann wird die Doku von Rating B auf Rating A umgestellt."
else
  echo "❌ Mindestens ein Schritt schlug fehl (Exit $RC) — Output oben"
  echo "   bitte in den Chat kopieren."
fi
echo
read -r -p "Enter zum Schließen..." _
