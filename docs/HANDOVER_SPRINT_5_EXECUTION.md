# HANDOVER — Sprint 5 Umsetzungsphase (für den nächsten, sauberen Chat)

**Stand:** 2026-06-09. Macht dich (die nächste Session) sofort arbeitsfähig. Planung
und Design für Sprint 5 sind **abgeschlossen**; ab jetzt wird blockweise gebaut +
gemessen. Lies zuerst dieses Dokument, dann die verlinkten Detailpläne.

## 0 — Orientierung
MLB-Saison-Optimierer, 30 Teams, 2.430 Spiele. Mit Jonas **immer Deutsch**. Maßstab:
MLB muss es direkt nutzen können. Arbeitsstil: durchdenken → recherchieren → **messen
statt behaupten** → Qualität vor Tempo. Determinismus nie brechen (neue Features
gegated, Default off → bit-identisch). Jeder Block endet mit einer **Messung gegen den
realen 2024- UND 2025-Plan**.

## 1 — Verbindliche Entscheidungen (NICHT umstoßen)
1. **AC-2.1.8 (≤13 Tage auswärts) ist WEICH**, kein CBA-Erfordernis (verifiziert: nicht
   in CBA Article V). Das harte Muss ist **AC-2.1.9 / V(C)(12) = ≤20 konsekutive
   Spieltage** (bereits strukturell garantiert). Q10 / ≤13-Branch-and-Price ist
   **obsolet**. Doku: `regulations/FINDING_AC-2.1.8_vs_CBA.md`.
2. **FORK 1 = Startzeiten modellieren** (ambitioniert). Startzeit wird Modell-Dimension
   → V(C)(6)–(9) hart durchsetzbar, TV-Fenster werden harte Constraints. Design steht:
   `docs/SPRINT_5_1_STARTTIME_DESIGN.md`.
3. **FORK 2 = green-field From-Scratch wird Produktziel** (ambitioniert). Branch-and-Price
   / Gurobi für die **echten** harten Regeln (nicht für ≤13). Braucht Gurobi Academic
   License (Jonas, Uni-WLAN) + Balanced-Schedule-Format-Regeln.

## 2 — Was bereits gebaut & verifiziert ist (diese Session)
- **5.0 Cleanup ✅** — AC-2.1.8 → `severity="soft"` in `compliance.py`; xfail-Test
  umgewidmet (`test_AC_2_1_8_ist_weiches_qualitaetsziel_...`); Q10 in
  `REFACTOR_BACKLOG.md` geschlossen; Docs-Sweep (CBA_DEFINITIONS, README). Verifiziert:
  Compliance 21/21, Fatigue 19/19, Sprint-4+QA 31/31.
- **A1 — V(C)(11) PT→ET-Off-Day ✅** — neue harte Regel `CBA-PTET` (+
  `_check_pt_et_offday`) in `compliance.py`, in den Report verdrahtet. Konservativ (≤7-
  Liga-Ausnahme = startzeit-abhängig → nicht modelliert, strikter Default). **Gemessen:
  realer 2024+2025-Plan = 0 Verstöße.** 3 neue Tests, Suite 24/24 grün.
- **Appendix C transkribiert & verifiziert ✅** — `data/appendix_c_travel_times.json`
  (30×30, Projekt-IDs CHC/KCR/SDP/SFG/TBR/WSN, CWS=White Sox). Voll symmetrisch
  (0 Mismatches/406 Paare), Anker LAD-ATL=3:52, LAD-CIN=3:48, LAA-LAD=:03, OAK-SFG=:01,
  12 Stichproben OK. Verifier: `tools/transcribe_appendix_c.py`.
- **5.1 Startzeit-Fundament ✅** — `src/start_times.py` (gegated, deterministisch, kein
  RNG): `AppendixC`-Lookup, V(C)(8)-Getaway-Formel, `assign_start_times`,
  `validate_getaway_times`/`validate_nightday_times`/`validate_day_min_times`,
  `load_real_start_times` (UTC→Lokalzeit, DST-korrekt). Drei neue Compliance-Regeln
  (gegated über `start_min`): `STARTTIME-GETAWAY` (V(C)(8), hart), `STARTTIME-NIGHTDAY`
  (V(C)(9), hart), `STARTTIME-DAYMIN` (V(C)(6), **weich**). **Gemessen real 2024+2025:**
  V(C)(8) 0 Verstöße (±40 min per-Club First-Pitch-Konvention; reise-bindende Fälle
  inflight>2:30 exakt reproduziert), V(C)(9) 0 (mit Feiertag/Home-Opener/Cubs-Ausnahmen;
  die 3 Roh-Treffer 2025 = exakt diese Ausnahmen), V(C)(6) nur dokumentierte Früh-Specials
  (Patriots'/Education/Holiday). Default-Pfad bit-identisch (Regeln ohne `start_min`
  übersprungen). 17 neue Tests grün; Regression Compliance/Fatigue/Sprint-4/QA (74) +
  Invarianten (5) grün. Details: `regulations/SPRINT_5_1_STARTTIME_MEASUREMENT.md`.
  **HINWEIS:** 2025-Baseline-Report ist NICHT hart-konform (SCHED-162/SCHED-HA aus
  as-played-Artefakten) — unabhängig von 5.1; die Startzeit-Schicht fügt keinen neuen
  harten Verstoß hinzu.
- **5.2 Compliance-Vollständigkeit ✅** — `src/schedule_rules.py` (V(C)(13) Off-Day-
  Verteilung, V(C)(14)/(15) DH-Limits) + Regeln `CBA-OFFDAY`/`CBA-DH` (weich, gegated
  über `schedule_kind`). Realdaten-Messung: nur as-played-Artefakte (V(C)(13) 12/8,
  V(C)(14) 2025=4 Makeups, V(C)(15) 0). **Querschnitt-Fix:** gegateter SA-Penalty
  `feas_w_ptet` schließt die stille `CBA-PTET`-Lücke des Optimierers (Default off →
  bit-identisch). 14 Tests grün. Doku `regulations/SPRINT_5_2_COMPLIANCE_MEASUREMENT.md`.
- **5.3 Daten (analysierbarer Kern) ✅** — **E2 gelöst:** 2025 schwächer, weil der
  reale 2025-Plan fatigue-belasteter startet (TBR 14 away-days >13 + 20 games-no-off,
  Hurricane-Milton-Relokation → Steinbrenner Field); der SA gibt das beste Ergebnis nach
  ENERGIE (λ_fat=1e6) zurück → Budget fließt in Fatigue statt km. 2024 startet sauber
  (max 11). Entry-km==Season-km (kein Messartefakt). Tool `tools/diagnose_e2_2025.py`.
  **C6 geklärt:** Kalibrier-Basis = Sportico/Statista-2024-Gate/Heimspiel (`base_team`);
  ESPN-Attendance ist NUR Validierung (Spearman 0,892), kein Kalibrier-Input. **E1
  assessed:** Kern-Reise = Haversine (deterministisch, kein Netz) → erfüllt; ORS nur für
  Ops-Routing (5.5, noch nicht verdrahtet) → Cache-Empfehlung dokumentiert. Doku
  `regulations/SPRINT_5_3_DATA_FINDINGS.md`. OFFEN (externe Daten): C1 Gate-Receipts,
  C2 TV-Fenster, C3 Venue-Konzerte.
- **5.4 green-field + B3 ✅ (Solver-Kern + Lizenz-Plumbing)** — `src/balanced_schedule.py`
  (MLB-2023+-Format als Constraints; real 2024 = 0 Verstöße) + `src/greenfield_gurobi.py`
  (TTP-MIP, reale km, B3-Quoten, V(C)(12); reduziert OPTIMAL in 0,3 s). **Lizenz „nur Key
  reinpasten":** `.env` → `GRB_WLSACCESSID/SECRET/LICENSEID` (oder `GRB_LICENSE_FILE`);
  `src/config.get_gurobi_wls()` lädt automatisch. Ohne Lizenz Restricted (klein); größer →
  klare Meldung. Demo `tools/greenfield_demo.py`. Voll-Saison = TTP-hart → Lizenz hebt
  Größenlimit, B&P-Dekomposition ist der Skalierungspfad (HAP-Gerüst in `src/colgen`).
- **5.5 D1–D3 Chronobiologie ✅** — `src/chronobiology.py`: konservativ diskontierte
  (0.25), evidenzbasierte (PNAS 2017), faire/symmetrische Jet-Lag-Gewichte (Ostwärts>West);
  reine Analyse-Schicht (Default-Pfad bit-identisch). Real 2024 total≈422/Gini 0,19; West-
  Teams am stärksten belastet (richtungs-sensitiv). 9 Tests. Doku
  `regulations/SPRINT_5_4_5_5_GREENFIELD_CHRONO.md`.
- **Branch-and-Price-Engine ✅** — `src/branch_and_price.py`: Dantzig-Wolfe nach Team
  (Spalte=Einzel-Team-Plan), Gurobi Set-Partition-Master mit Game-Consistency-Coupling +
  Pricing-Subproblem + Price-and-Branch; greedy Bootstrap (nie schlechter) + `seed_schedules`.
  Validiert reduziert: gültig/matchup-komplett/konsistent; **mit Seed erreicht der integer
  Master das monolithische Optimum**. Demo `--method bnp`. **Korrektur-Befund dabei:** der
  monolithische green-field Solver unter-zählte Reise (kein Off-Day-Persistenz/Anker) →
  **gefixt** (echte km, monolithisch == decomposed). Ehrlich: reines CG schlägt Bootstrap auf
  engen Mini-Instanzen kaum (Koordinationslimit = B&P-Forschungsfront; nächster Schritt
  Branching/runden-basiert). 4 B&P-Tests. Skaliert mit Jonas' Key.
- **Echtes B&P-Branching + Fenster-Dekomposition ✅** — `branch_and_price_optimal`
  (DFS-Event-Branching, CG je Knoten, Bounding; korrekt, erreicht Optimum mit Seed).
  **Präziser Forschungs-Befund:** reines per-Team-CG verbessert strukturell NICHT über
  Bootstrap (Spalten verschiedener Pläne sind untereinander inkonsistent; konsistente
  verbessernde Sets brauchen gemeinsame Erzeugung — Grund, warum TTP-B&P trip-/runden-
  basiert dekomponiert wird). **Praktischer Skalierer = `src/greenfield_decomp.py`**
  (Rolling-Horizon-Fenster, team-gekoppelte Sub-MIPs, Reise-Kontinuität, ≤-Bootstrap-
  Garantie): liefert gültige Pläne **wo monolithisch am Größenlimit scheitert** (4 Teams:
  −2,4 % vs Bootstrap, 0,45 s). Demo `--method bnp|windowed`. 6 B&P- + 3 Decomp-Tests grün.
- **Trip-/Pattern-basiert (runden-indiziert) ✅** — `src/ttp_rounds.py`: kompaktes
  runden-indiziertes TTP-MIP (jede Mannschaft 1×/Runde = HAP-Pattern; Roadtrip-Limit als
  Constraint; R=gpp·(n−1) ≪ Tage). **Löst n=4 OPTIMAL (gap 0, 0,12 s) — wo das tag-
  indizierte MIP am Restricted-Größenlimit scheitert**; Resultat = Fenster-Heuristik
  (kreuz-validiert Optimalität). `rounds_to_days()` für Tages-Mapping. Demo
  `--method rounds`. n≥6 braucht Lizenz. 5 Tests grün. **= der korrekte Voll-Saison-
  Kern** (pattern-basiert, nicht per-Team).

## 3 — Offene Blöcke (Reihenfolge = Roadmap)
Detailplan je Gap: `docs/SPRINT_5_REMEDIATION_PLAN.md`. Gap-Register:
`docs/SPRINT_5_GAP_REGISTER.md`. Daten-Befunde: `docs/SPRINT_5_DATA_FINDINGS.md`.

**~~ERSTER JOB: Appendix-C-Transkription~~ ✅ ERLEDIGT** (Mapping fixiert: `CWS` bleibt
`CWS` = White Sox; `CHI`→`CHC`, `KC`→`KCR`, `SD`→`SDP`, `SF`→`SFG`, `TB`→`TBR`,
`WSH`→`WSN`). Verifiziert (Symmetrie/Anker/Stichprobe). Siehe Stand-Block oben.

**~~5.1 — Startzeit-Fundament~~ ✅ ERLEDIGT.** Siehe Stand-Block oben +
`regulations/SPRINT_5_1_STARTTIME_MEASUREMENT.md`. Design war:
`docs/SPRINT_5_1_STARTTIME_DESIGN.md`.

**~~5.2 — Compliance-Rest~~ ✅ ERLEDIGT (2026-06-10).** `src/schedule_rules.py`:
V(C)(13) Off-Day-Verteilung + V(C)(14)/(15) DH-Limits, als SOFT-Regeln `CBA-OFFDAY`/
`CBA-DH` verdrahtet (Originalplan-Regeln; auf as-played informativ — gemessen nur
Makeup-/Rainout-Artefakte, keine echten Verstöße). **WICHTIGER BEFUND+FIX:** der
SA-Optimierer (`optimize_travel`) erzeugte einen stillen `CBA-PTET`-Verstoß (V(C)(11)) →
neuer **gegateter** SA-Penalty `feas_w_ptet` (OptimizerConfig/optimize_pareto, CLI
`--feas-ptet`; Default 0 → bit-identisch; wirkt nur mit `feas_lambda>0`, empf. ~100).
Post-Output-Property-Test belegt: kein neuer harter Verstoß. V(C)(5) als Datengrenze
dokumentiert (Day-DH-Typ nicht im Loader). A2/V(C)(13) damit als **Guard** geschlossen.
Doku `regulations/SPRINT_5_2_COMPLIANCE_MEASUREMENT.md`. 14 neue Tests + Regression grün.

**OFFEN — nur noch extern-blockiert (Jonas):**
1. **Gurobi-Key eintragen** (`.env`: `GRB_WLSACCESSID/GRB_WLSSECRET/GRB_LICENSEID`) →
   green-field Solver löst dann größere Instanzen (Code steht, „nur Key reinpasten").
   Voll-30-Team = TTP-hart → nächster Forschungsschritt B&P-Dekomposition (B3-Matrix +
   MIP-Bausteine vorhanden).
2. **Daten-Items C1/C2/C3/C5:** Forbes-Gate-Receipts, verifizierte Broadcaster-TV-Fenster,
   Co-Tenant-Venue-Pläne (River Cats/Tarpons 2025), Club-Hotel-/Routing-Realdaten + optional
   Maps-API. Alle Code-Schnittstellen stehen (TV-Pins via `assign_start_times(tv_pins=…)`,
   `event_conflicts`, Ops-Suite, ORS-Cache-Empfehlung) — es fehlen nur die externen Daten.
**Damit ist der komplette ohne-externe-Abhängigkeiten machbare Sprint-5-Scope (5.0–5.5)
umgesetzt + gemessen.** Optional weiter: B&P-Dekomposition (sobald Gurobi-Key da),
ORS-Cache fürs Ops-Routing, Daten-Einpflege.

**5.2 — Compliance-Rest:** A3 (Startzeit-Regeln, nach 5.1), A4 (DH-Limits V(C)(14)/(15));
**A2 (V(C)(13) Off-Day-Verteilung) ist BLOCKIERT** — Schedule-JSONs sind „as-played"
(Makeups/Intl/Relokationen), Off-Day-Verteilung darin ist artefaktbehaftet
(`finding-as-played-data`). Entscheidung offen: A2 nur als Guard auf Optimierer-Output
ODER original veröffentlichte Schedules beschaffen. **Querschnitt:** Post-Move-Validierung
des SA gegen alle harten Regeln (Property-Test).

**5.3 — Daten:** C1 (Gate/Forbes + Sensitivität), C2 (TV pro Spiel, jetzt hart an Slots),
C3 (Venue: geteilte 2025-Venues exakt — River Cats/Tarpons), C6 (Revenue-Kalibrierung
klären: was nutzt `revenue_model.json`?), E1 (ORS → eingefrorener Cache → Haversine).
ORS-Key liegt in `.env` (`ORS_API_KEY`).

**5.4 — Green-field:** Branch-and-Price/Gurobi (Lizenz nötig), B3 Balanced-Schedule-Format,
E2-Diagnose (warum 2025 −2,6 % vs. 2024 −5,4 %; teils geklärt: 2025-Daten unsauberer).

**5.5 — Ops & Fundierung:** Ops-Suite-Realdaten (C5), D1–D3 Chronobiologie-Gewichte
(PNAS 2017 etc., konservativ diskontiert, fair/symmetrisch).

## 4 — Sandbox-/Test-Setup (in dieser Session etabliert)
- `pip install pytest ortools==9.10.4067 numpy pandas geopy python-dateutil tzdata --break-system-packages`
- Tests/Skripte aus dem Projektroot mit `PYTHONPATH="$(pwd)"` und `PATH="$HOME/.local/bin:$PATH"`.
- Schnelle Suites: `python -m pytest -m "not slow" -q -p no:cacheprovider tests/<file>.py`.
  CP-SAT-Generierungstests sind langsam → einzeln/zeitlich begrenzt laufen.
- Realen Plan laden: `LocalFileAdapter(base_dir="data").fetch_season_schedule(2024)`.

## 5 — Konventionen (NICHT brechen)
Determinismus (num_search_workers=1 + Seed → bit-identisch); neue Features gegated;
Daten-Ehrlichkeit (echt/Proxy/Seed markiert, Admiralty-Rating); jede neue harte Regel ↔
Verbatim-Zitat aus `regulations/CBA_2022-2026_Article_V_Scheduling.md`; pro Block ein
Review-/Mess-Eintrag.

## 6 — Alle Sprint-5-Dokumente
- `docs/SPRINT_5_PLAN.md` — Ur-Plan (5.1–5.4, vor den Befunden).
- `docs/SPRINT_5_GAP_REGISTER.md` — ehrliche Lückenliste A–G.
- `docs/SPRINT_5_REMEDIATION_PLAN.md` — Maßnahmenplan A–G + Roadmap + **Live-Fortschritt (2b)**.
- `docs/SPRINT_5_RESEARCH_METHODOLOGY.md` — wissenschaftliches Recherche-Protokoll.
- `docs/SPRINT_5_DATA_FINDINGS.md` — konkrete Daten (TV, CBA, Venue, Chrono, Special).
- `docs/SPRINT_5_1_STARTTIME_DESIGN.md` — Startzeit-Architektur.
- `regulations/` — CBA Article V verbatim, AC-2.1.8-Befund, Appendix-C-README, INDEX.
