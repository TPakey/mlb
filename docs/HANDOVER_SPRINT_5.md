# HANDOVER — Stand nach Sprint 4 (2026-06-08, autonome Nacht-Session)

**Für die nächste Session.** Macht dich sofort arbeitsfähig. Lies zuerst dies, dann
`docs/SPRINT_4_REVIEW.md` (Details + Messungen) und das Projekt-Gedächtnis.

## 0 — Orientierung (unverändert)

MLB-Saison-Optimierer, 30 Teams, 2.430 Spiele. Pipeline: realer Plan →
**Warm-Start** (`optimize_travel`) → optional Pareto-Front. Warm-Start ist der
**einzige Produktionspfad** (P0). Mit Jonas immer **Deutsch**. Maßstab: MLB muss es
direkt nutzen können. Arbeitsstil: durchdenken → recherchieren → **messen statt
behaupten** → Qualität vor Tempo. Determinismus nie brechen (neue Features gegated).

## 1 — Was Sprint 4 dazubrachte (diese Nacht, alles getestet + dokumentiert)

Alle „ohne externe MLB-Daten machbaren" offenen Punkte aus dem Sprint-4-Handover
abgearbeitet. Voller Bericht: `docs/SPRINT_4_REVIEW.md`.

1. **TTP-Nachbarschaft OROPT** (`move_mix_oropt`, `--oropt-share`): OR-opt/Best-
   Insertion-Geo-Move. **Ehrlich vermessen → kein Produktions-Win** (früh minimal
   besser, bei ≥300k Iter schlechter als der stochastische GEO-Move). Bleibt
   gegated/**off**, getestet, dokumentiert. Erkenntnis: km-Hebel liegt nicht in
   gierigeren Einzel-Moves.
2. **DH-Compression v2** (`compress_with_pullin`, `enable_pullin`): Compression +
   Pull-in greift auch, wenn die letzte Trip-Serie nur 1 Spiel hat. Matchup-
   erhaltend, atomar validiert, gegated.
3. **Harter Venue-Belegungskalender**: Verifikation `event_conflicts.venue_conflicts`
   + Compliance-Regel **VENUE-AVAIL** (hart, opt-in). Durchsetzung lief schon über
   `home_blackout_days` (E2E-getestet). Daten illustrativ (2026), Mechanik
   datenunabhängig.
4. **Ops-Dossier ins Dashboard**: `dashboard/build_ops_dashboard.py` →
   `dashboard/ops.html` (30 Teams, 811 Stadt-Dossiers, self-contained, verlinkt aus
   index.html).
5. **Härtung**: korruptes JSON → klare `DataSourceError`; CLI-Arg-Validierung
   (`main._validate_args`).

## 2 — Belastbare Kennzahlen (Sprint-4-QA, gemessen)

Nicht-Slow-Suite **373 passed / 1 xfail / 0 Fehler**. Determinismus bit-identisch
(Default + feas/holiday on), inkl. voller Spiel-Signatur. Realer 2024-Plan voll
compliant inkl. VENUE-AVAIL. Warm-Start 500k Iter −3,54 % (6M → −5,4 %), 0
CBA-Verletzungen. Revenue Spearman 0,892.

## 3 — Konventionen (NICHT brechen)

- Determinismus: `num_search_workers=1` + fixer Seed → bit-identisch. Neue
  Sprint-4-Features alle gegated (Default off) → bit-identisch zum bisherigen Stand.
- Tests: `python -m pytest -m "not slow" -q -p no:cacheprovider` (in der Sandbox
  in 3–4 Gruppen splitten, je < 45 s). Sprint-4-Tests: `tests/test_sprint_4.py`.
- Sandbox: kann nicht löschen (überschreiben), `pip install --break-system-packages`,
  lange SA-Läufe splitten.

## 4 — Was noch offen ist = NUR externe Daten/Beschaffung (Jonas/MLB-Ops)

Keine reinen Code-/Algorithmik-Punkte mehr offen, die ohne externe Daten sinnvoll
sind. Verbleibend (unverändert seit Sprint 3, das sind die echten „100 %"-Blocker):

1. **National-TV-Fenster** (ESPN/FOX/TBS-Exklusivslots) als harte Anforderung —
   echte Broadcaster-Daten nötig.
2. **Venue-Belegungskalender mit echten, jahresgleichen Daten** — Mechanik steht
   (VENUE-AVAIL + `home_blackout_days`), nur die Daten sind illustrativ.
3. **Echte Gate-Receipts** statt Attendance-Proxy (MLB-interner Report) — zum
   Pro-Spiel-Validieren des Revenue-Modells.
4. **CBA-Wortlaut AC-2.1.8** (Reisetag-Zählung) von MLB-Ops bestätigen.
5. **Club-Hotel-Buchungshistorie** + Maps-API + lokale EMS/PD-Liaison für die
   Ops-Suite (Schemata/Felder stehen, Seeds klar markiert).

**Beschaffungs-gegatet (optional):** Branch-and-Price/Gurobi für echte
From-Scratch-Pläne (nicht nötig, solange Warm-Start der Produktionspfad ist).

## 5 — Schnellbefehle

```bash
# Produktionsplan (Warm-Start):
python -m src.main --source-season 2024 --geo-topk 6 --feas-lambda 50000 --holiday-lambda 5000
# Ops-Dashboard neu bauen:
python dashboard/build_ops_dashboard.py --season 2024
# Compliance inkl. Venue-Check:
python -c "from src.datasources import LocalFileAdapter; from src.data_loader import load_teams, teams_by_id; from src.compliance import compliance_report; s=LocalFileAdapter(base_dir='data').fetch_season_schedule(2024); print(compliance_report(s, sorted({g.home for g in s.games}), teams_by_id(load_teams()), check_venue=True).is_compliant)"
# Schnelle Tests (gruppiert):
python -m pytest -m "not slow" -q -p no:cacheprovider tests/test_sprint_4.py
```
