#!/bin/bash
# ============================================================
#  Git-Repo aus dem Nacht-Härtungs-Bundle herstellen (Doppelklick)
#  Hintergrund: Die Sandbox konnte im Projektordner keine Git-Locks
#  löschen (Mount-Restriktion) — die komplette Commit-Historie der
#  Nacht-Session liegt deshalb im Bundle. Dieses Skript macht daraus
#  das echte Repo IM Projektordner. Danach: GitHub-Remote anlegen.
# ============================================================
set -u
cd "$(dirname "$0")" || exit 1

if [ -d .git ] && git rev-parse HEAD >/dev/null 2>&1; then
  echo "ℹ Es existiert bereits ein funktionierendes Git-Repo — nichts zu tun."
  read -r -p "Enter zum Schließen..." _; exit 0
fi

# kaputtes Sandbox-.git entsorgen (auf dem Mac normal löschbar):
rm -rf .git .git_broken_sandbox_DELETE_ME 2>/dev/null

# Neuesten Bundle automatisch waehlen (Finalisierung 2026-06-14: das neue Bundle
# enthaelt zusaetzlich die Headline-/Guard-/Anker-Commits).
BUNDLE="$(ls -t *.bundle 2>/dev/null | head -1)"
if [ -z "$BUNDLE" ] || [ ! -f "$BUNDLE" ]; then
  echo "❌ Kein .bundle gefunden."; read -r -p "Enter..." _; exit 1
fi
echo "→ Verwende Bundle: $BUNDLE"

git init -b main >/dev/null && \
git remote add bundle "$BUNDLE" && \
git fetch bundle main >/dev/null 2>&1 && \
git reset --soft bundle/main && \
git remote remove bundle && \
echo "✅ Repo hergestellt:" && git log --oneline | head -12 && \
echo "" && \
echo "WICHTIG: Arbeitsstand == letzter Commit? ->" && git status --short | head -5 && \
echo "" && \
echo "Nächste Schritte (GitHub, ~2 Min):" && \
echo "  1) Auf github.com ein privates Repo 'mlb-logistics-optimizer' anlegen" && \
echo "  2) git remote add origin git@github.com:<du>/mlb-logistics-optimizer.git" && \
echo "  3) git push -u origin main   -> CI (inkl. nightly slow-Suite) läuft an"
read -r -p "Enter zum Schließen..." _
