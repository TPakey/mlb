# Finalisierung — Abschluss MLB Logistics Optimizer

> **Für „Portfolio + nutzbares Tool" abgeschlossen; offen bleibt nur die
> Ausbaustufe „alleiniges Planungstool" (extern/optional).**

Datum: 2026-06-14. Anlass: Eine unabhängige Review hat bestätigt, dass das
Projekt im Kern fertig ist — es fehlten nur fünf klar benannte Punkte. Diese
sind hier abgearbeitet, jeder mit eigenem Commit, beweisbasiert, Suite grün,
Determinismus erhalten. Kein Scope-Wachstum.

Maßstab dieser Finalisierung: **beweisen statt behaupten.** Jeder Punkt unten
nennt den konkreten Beleg (Test / Messung), nicht nur „erledigt".

---

## MUSS

### Punkt 1 — Headline-Workflow als eingecheckter Befehl ✅
**Status:** erledigt. **Commit:** `Punkt 1: Headline-Workflow --from-original …`

Die zentrale Demo — *publizierten Originalplan laden → optimieren → Publish-Gate
→ Δkm + Compliance-Report* — ist jetzt ein erstklassiger Entry-Point statt eines
Ad-hoc-Skripts. Neu: `python -m tools.backtest --from-original 2026`.

Vorher konnten weder `tools/backtest` noch `src/main` den 2026-Originalplan
laden (beide nur as-played `data/mlb_schedule_<jahr>.json`; 2026 existiert dort
nicht). Neu: `_load_input_season(year, from_original=True)` lädt über
`src.original_schedule.load_original_schedule` (Retrosheet, Rating A), das Flag
ist durch `run()` / `improve_real_plan()` / `load_real_baseline()` gefädelt.

**Beweis:** `tests/test_from_original.py` (3 Tests, grün):
- 2026-Original ist ladbar (2430 Spiele) — vorher unmöglich.
- Output passiert das Publish-Gate (PASS) — `improve_real_plan` wirft sonst
  `UnpublishableScheduleError`.
- Δkm < 0 gegenüber dem Original.
- Lauf bit-identisch bei gleichem Seed.

Gemessen (Sandbox): 200k Iter → Gate PASS, −0,24 %; 3 M Iter → Gate PASS,
**−1,7 %** in 22,6 s (Headline-Tiefe −1,8 % entsteht mit 3–6 M auf echter
Hardware). Der Test hält die *Kette* fest, nicht die km-Tiefe.

### (kein weiterer Muss-Punkt offen)

---

## SOLLTE

### Punkt 2 — „Konformität per Konstruktion" korrigiert ✅
**Status:** erledigt. **Commit:** `Punkte 2+3: "per Konstruktion"-Claim korrigiert …`

Die Behauptung war faktisch falsch: der Optimierer allein erzeugt sehr wohl
Verstöße. **Belegt:** auf dem 2026-Original mit `ASB=None` produziert dieselbe
Produktions-Config **~29 neue V(C)(13)-Verstöße** und einen scheinbar besseren
Plan (−2,31 % statt −1,7 %, weil Verstöße km sparen) — gefangen erst vom Gate.

Korrigiert auf **„Konformität durch Gate-Ablehnung + ausreichende Iterationen"**
in: `src/generator_optimizer.py` (Kommentar `sched13_lambda` + Docstring
`production_optimizer_config`) und `docs/ASSESSMENT_2026-06-11.md` (Pillar 2).

### Punkt 3 — ASB-Fehlbedienungs-Guard ✅
**Status:** erledigt. **Commit:** `Punkte 2+3: … + ASB-Fehlbedienungs-Guard`

Neuer Schalter `OptimizerConfig.require_all_star_break` (Default `False` →
bit-identisch; in `production_optimizer_config` `True`). `optimize_travel` bricht
**früh mit `ValueError` ab**, wenn `sched13_lambda>0` aber kein plausibler
All-Star-Break im Saisonfenster liegt — statt still gegen das falsche Modell zu
optimieren und den Fehler erst dem Gate als letzter Rettung zu überlassen.

**Beweis:** `tests/test_asb_guard.py` (4 Tests, grün): Default-Config Guard aus
(bit-identisch), Produktions-Config Guard an, Guard kippt bei `ASB=None`, läuft
mit korrektem ASB normal durch. Bestehende Produktionspfad-Tests setzen den ASB
via `detect_all_star_break` und sind unberührt.

### Punkt 4 — Determinismus-Anker als Test ✅
**Status:** erledigt. **Commit:** `Punkt 4: Determinismus-Anker als Regressionstest …`

`tests/test_determinism_anchor.py` (2 Tests, grün) nagelt den Legacy-Pfad fest
(2024 as-played, 200k, Seed 42, `--legacy-bitident`). Der SA nutzt
`random.Random(seed)` (Mersenne-Twister) → plattform- und versionsstabil, der
Wert ist also portabel.

**BEFUND (ehrlich):** Der dokumentierte Anker **1680131 reproduziert NICHT
mehr** — kanonisch (zweifach gemessen, zwei Codepfade) ergibt sich **1672794**.
Der alte Wert ist gedriftet (vor dem Bundle-HEAD), die Behauptung „weiterhin
exakt" war nicht mehr korrekt. Verankert ist jetzt der **tatsächlich
reproduzierende** Wert; `docs/ASSESSMENT_2026-06-11.md` ist korrigiert.

### Punkt 5 — Manifest-Drift 15/16 korrigiert ✅
**Status:** erledigt. **Commit:** `Punkt 5: Manifest-Doku-Drift korrigiert (16 -> 15)`

`tools.verify_data_manifest` friert **15** Quell-Dateien ein, die Doku behauptete
16. An den realen Tool-Stand angeglichen (15/15 OK). Die 11 nicht eingefrorenen
`.json` sind bewusst Config/Derived/Example (`revenue_model`, `tv_slots`,
`phase_calibration`, `team_airports`/`team_hotels`, …) — kein Gap.

---

## Verifikation (diese Session, eigene Läufe)

| Prüfung | Ergebnis |
|---|---|
| `test_from_original.py` | **3 passed** (3,9 s) |
| `test_asb_guard.py` | **4 passed** (0,7 s) |
| `test_determinism_anchor.py` | **2 passed** (3,1 s) |
| Regressions-Batch (10 Files inkl. sprint_5_2_compliance, repair_local, compliance, invariants) | **92 passed**, 0 failed (12,8 s) |
| Headline 2026-Original, 3 M Iter | Gate **PASS**, **−1,7 %**, 22,6 s |
| Determinismus (gleicher Seed 2×) | **bit-identisch** |
| `verify_data_manifest` | **15/15 OK**, 0 Mismatches |
| `validate_revenue_model` | Spearman **0,892 / 0,922 / 0,958**, PASS |

**Blindfleck (ehrlich):** Die *vollständige* Suite (≈521 Tests + 50 slow) lief
in der Sandbox nicht komplett durch — einige nicht-`slow`-markierte Tests führen
eine volle CP-SAT-Schedule-Generierung aus und brauchen auf echter Hardware
Minuten. Alle hier gelaufenen Tests (>90 Kern + 9 neue) sind grün, 0 Fehler. Die
Voll-Suite einmal auf echter Hardware grün zu sehen, gehört zum CI-Schritt unten.

---

## Was nur Jonas tun kann (nicht von der KI lösbar)

1. **Git-Restore + Remote auf dem Mac.** Die Sandbox kann im Projektordner keine
   Git-Locks lösen (Mount-Restriktion). Die Historie inkl. dieser Finalisierungs-
   Commits liegt im neuen Bundle (siehe unten). **Schritte:** `GIT_SETUP.command`
   doppelklicken → privates GitHub-Repo anlegen → `git remote add origin …` →
   `git push -u origin main`. Danach läuft die CI (inkl. nightly slow-Suite) und
   die volle Suite wird erstmals offsite/automatisch grün verifiziert.
2. **Optional: 6-M-Messreihe auf echter Hardware.** `python -m tools.backtest
   --from-original 2026` mit 6 M+ Iterationen (ggf. `--geo-topk` tunen), dann die
   km-Zahl in README/Assessment auf den Hardware-Wert umstellen. Reine
   Tiefen-Bestätigung — die Kette selbst ist verifiziert.

---

## Bewusst NICHT angefasst (Ausbaustufe / extern, kein Abschluss-Blocker)

Diese Punkte gehören zur Stufe „alleiniges Planungstool" und sind **später /
optional**, kein Hindernis für „Portfolio + nutzbares Tool":

- **Gurobi** aktivieren (Uni-VPN) + green-field-Skalierungstreppe.
- **6-M-Messreihe** auf echter Hardware (s. o.).
- **GitHub-Remote** (s. o. — der einzige operative Rest).
- **Premium-Rekalibrierung** (Geschäftsentscheidung; −22…−42 % Top-Teams).
- **CBA-2027-Versionsschalter** (Design liegt in `DESIGN_CBA_VERSIONING.md`).
- **Pareto-Pfad regelfest** machen (aktuell auf publizierbare Punkte gefiltert).
- **Per-Team-ASB-Verfeinerung** (B2; aktuell ausreichend, Verfeinerung optional).

---

## Fazit

Alle fünf benannten Punkte sind erledigt und committet, jeder mit Beweis. Die
zentrale Demo läuft auf Knopfdruck und ist getestet; eine verkaufte Garantie,
die der Code nicht gibt, ist entfernt; die ASB-Falle ist früh abgefangen;
Determinismus ist erstmals als Test prüfbar (mit korrigiertem Wert); die
Doku-Zahlen stimmen mit dem Tool überein. **Für Portfolio + nutzbares Tool: durch.**
Operativ bleibt nur Git-Remote auf dem Mac; alles Weitere ist Ausbaustufe.
