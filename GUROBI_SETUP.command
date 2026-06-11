#!/bin/bash
# ============================================================
#  MLB Logistics Optimizer — Gurobi-Lizenz einrichten (Doppelklick)
#  WICHTIG: Im UNI-NETZ (oder Uni-VPN) ausführen — der Aktivierungs-
#  code ist EINMALIG und bindet die Lizenz an diesen Mac.
#  Ablauf: grbgetkey ausführen → .env schreiben → Voll-Lizenz mit
#  einem Beweis-Solve über dem Restricted-Limit validieren.
# ============================================================
set -u
cd "$(dirname "$0")" || exit 1

KEY="5761e08e-47b0-440d-af35-2a97cc22fa3b"
PY="$(command -v python3 || echo /usr/bin/python3)"
export PYTHONPATH="$(pwd)"

echo "Projektordner: $(pwd)"
echo

# gurobipy wird fuer den Validierungs-Solve gebraucht:
if ! "$PY" -c "import gurobipy" 2>/dev/null; then
  echo "→ installiere gurobipy (einmalig) ..."
  "$PY" -m pip install --user gurobipy || {
    echo "❌ pip install gurobipy schlug fehl — Output bitte in den Chat kopieren."
    read -r -p "Enter zum Schließen..." _; exit 1; }
fi

"$PY" -m tools.setup_gurobi --key "$KEY"
RC=$?

echo
if [ $RC -eq 0 ]; then
  echo "✅ LIZENZ AKTIV + VALIDIERT. Erste Skalierungsmessung:"
  echo "   python3 -m tools.greenfield_demo --method rounds \\"
  echo "          --teams NYY,BOS,TBR,TOR,BAL,CLE --games-per-pair 2"
else
  echo "❌ Noch nicht fertig (Exit $RC). Die zwei haeufigsten Gruende:"
  echo "   1) NICHT IM UNI-NETZ (ERROR 303 oben): Code bleibt gueltig —"
  echo "      im Uni-WLAN oder per Uni-VPN erneut doppelklicken."
  echo "   2) grbgetkey fehlt: Gurobi-Voll-Paket von gurobi.com/downloads."
  echo "   Output oben bitte in den Chat kopieren."
fi
echo
read -r -p "Enter zum Schließen..." _
