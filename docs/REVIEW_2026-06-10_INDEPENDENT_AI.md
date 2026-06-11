# Unabhängiger KI-Review — MLB Logistics Optimizer

**Datum:** 2026-06-10 · **Reviewer:** unabhängige KI-Session (Briefing: `AI_REVIEW_BRIEFING.md`)
**Methode:** Code-Review + eigene Läufe (Test-Suite, Compliance 2024/2025, Determinismus-Nachweis,
produktionsidentische Warm-Start-Läufe mit 6 M Iterationen, Disruption-Experiment, Green-field-Demos).
Jeder Befund ist reproduzierbar; Repro-Schritte stehen jeweils dabei. Maßstab laut Briefing:
**direkt von einem MLB-Scheduler nutzbar** — nicht Demo-Niveau.

---

## 1 — Ehrlicher Status-Check

**Was nachweislich gut ist (selbst verifiziert):**

- **Determinismus hält.** Zwei identische SA-Läufe (Seed 42, 50 k Iter) liefern bit-identische
  Pläne; alle gegateten Terme (feas/ptet/holiday) sind bei Default-0 nachweislich wirkungslos
  (bit-identischer Output). Konvention 1 ist erfüllt.
- **Test-Suite grün.** 438/438 nicht-slow Tests bestehen (488 gesamt, 50 `slow`).
  pyflakes: nur triviale unused-imports, großteils in `legacy/`.
- **Compliance-Tooling ist ehrlich gebaut.** Provenance-Register mit Verbatim-CBA-Quellen,
  hart/weich-Einstufung nachvollziehbar begründet, AC-2.1.8-Entscheidung (weich) sauber
  dokumentiert und korrekt umgesetzt. Die dokumentierten Messwerte (2024 hart-konform,
  2025 nicht wegen as-played-Artefakten) habe ich exakt reproduziert.
- **Regelformeln stimmen mit dem CBA-Wortlaut überein**, wo sie existieren: V(C)(8)-Getaway-Formel,
  V(C)(9) inkl. der drei Ausnahmen, V(C)(12)-Zählung (DH = 1 Spieltag, konsekutive Kalendertage),
  V(C)(13)-Fenster, Appendix-C-Lookup (symmetrisch, Projekt-ID-Mapping).
- **Datenehrlichkeit überwiegend gegeben:** echte Quellen (MLB-Stats-API, Appendix C, ESPN-Attendance)
  vs. Proxys (Revenue-Modell, Spearman 0,892 validiert) vs. Seeds (`team_hotels`: nur 5 Teams,
  explizit als illustrativ markiert) sind unterscheidbar markiert.

**Aber: das zentrale Produktversprechen ist aktuell falsch.** `README.md:57` behauptet, der
Warm-Start-Produktionspfad verbessere den realen Plan „und bleibt voll CBA-konform (0 Verletzungen)".
Mein produktionsidentischer Lauf (Default-Konfiguration wie `tools/backtest.py --warm-start`,
6 M Iterationen, Seed 42) ergibt:

| Lauf | km | hart verletzt (eigenes Compliance-Tooling) |
|---|---|---|
| 2024 Default | −4,88 % | **CBA-PTET: 18 Verstöße** (Input: 0); +36 neue V(C)(13)-Verstöße; |
| 2025 Default | −2,46 % | **CBA-PTET: 28**, **FEAS-GETA** (harter Reise-Envelope), + as-played-Erbe; +30 neue V(C)(13) |
| 2024 mit `feas_w_ptet=100` (3 M) | −4,94 % | PTET 0 ✓ — aber **weiterhin 30 neue V(C)(13)-Verstöße** |

Der Optimierer kauft seine km-Ersparnis teilweise durch Regelverstöße, die das eigene
Compliance-Modul als **hart** führt. Ein MLB-Scheduler könnte keinen einzigen dieser
Output-Pläne veröffentlichen. **Realistischer Reifegrad: starkes Forschungs-/Analyse-Framework
mit produktreifem Mess- und Compliance-Instrumentarium — aber der Optimierungs-Output selbst
ist nicht abnahmefähig.** Der Green-field-Pfad ist zusätzlich Forschungsstadium (validiert bis
n=4 Teams; n=6 scheitert an der Restricted License, Voll-Saison ungelöst).

---

## 2 — Was falsch / schwach ist (nach Priorität)

### P0-1 · Produktionspfad erzeugt harte CBA-Verstöße — Headline-Claim falsch
**Beleg (reproduziert):** Warm-Start 2024, exakt die Konfiguration aus
`tools/backtest.py::improve_real_plan` (Seed 42, 6 M Iter, `fatigue_lambda=1e6`, alle Gates Default):
Output hat 18 PT→ET-Spieltagsfolgen ohne Off-Day → `compliance_report().hard_failures = ['CBA-PTET']`.
2025 zusätzlich `FEAS-GETA` (Back-to-Back jenseits 4200 km/3 TZ-Hops — feas-Gate ist Default 0).
**Warum das passiert:** Die SA-Energie kennt im Default nur km + Fatigue (≤13/≤20). V(C)(11),
der Reise-Envelope und V(C)(13)/(14)/(15) sind als Penalty zwar implementiert, aber **gegated mit
Default 0** — die Bit-Identitäts-Konvention wurde über die Regel-Korrektheit gestellt.
**Verschärfung:** Der Property-Test `test_optimizer_introduces_no_new_hard_violation`
(tests/test_sprint_5_2_compliance.py:169) testet **nur die gefixte Konfiguration**
(`feas_w_ptet=100`), nicht den Produktions-Default — er belegt also nicht, was Doku/README
suggerieren. `README.md:57` („0 Verletzungen") ist durch das eigene Tooling widerlegt.
**Repro:**
```bash
python3 - <<'EOF'
# Default-Warm-Start 2024 wie backtest, dann compliance_report auf Output
# (vollständiges Skript: siehe Abschnitt 6, exp_one.py)
EOF
```

### P0-2 · V(C)(13)-Guard existiert, wird aber im Produktionspfad nie aufgerufen
`schedule_rules.original_schedule_violations` wird in `compliance.py:689` als „harter Guard auf
Optimierer-Output" bezeichnet — tatsächlich wird die Funktion **nirgends im Produktionscode**
aufgerufen (einziger Aufrufer: ein Unit-Test mit 2-Team-Spielzeug-Saison,
tests/test_sprint_5_2_compliance.py:140). Gemessen: SA-Output 2024 enthält **36 neue**
V(C)(13)-Verstöße (z. B. „ATL: 5 Open Days im 7-Tage-Fenster ab 2024-08-20", Limit 2) — auch
**mit** aktiviertem PTET-Fix bleiben 30. Es gibt keinerlei SA-Penalty oder Move-Filter für
Off-Day-Verteilung. Doku ≠ Code.

### P0-3 · Disruption-Handler verletzt die zentrale Workload-Regel V(C)(12)
`repair_local._find_next_free_slot` prüft nur: Saisonfenster, ASB, beide Teams frei, Blackout.
**Nicht geprüft:** die 20-/24-Tage-Limits aus V(C)(12) — obwohl V(C)(12) das Rescheduling
explizit regelt („… rescheduling does not result in the home team playing more than twenty-four
consecutive dates", zudem: Makeup „to an open date in the same series, or … end of the same
series" + Road-Off-Day-Bedingung — beides nicht modelliert).
**Beleg (reproduziert):** StadiumBlackout NYY 2024-08-05..18 → `repair_local` liefert Plan mit
**25 konsekutiven Spieltagen für NYY** (Limit 20/24). `all_teams_pass_fatigue_constraints`
schlägt an — wird vom Orchestrator aber nicht aufgerufen; `hard_constraint_violations` im
Disruption-Report zählt nur unverlegbare Spiele. Das „in ≤60 s drei valide Antworten"-Versprechen
(disruption.py:7) stimmt so nicht: die Antworten sind nicht zwingend valide.

### P1-4 · Grundsatzkonflikt: Bit-Identität schlägt Regelkorrektheit
Der in Sprint 5.2 **selbst gefundene** stille CBA-PTET-Verstoß wurde per gegatetem Flag gefixt
(Default off), damit alte Outputs bit-identisch bleiben. Konsequenz: der ausgelieferte Default
bleibt wissentlich regelverletzend. Meine Messung zeigt: der Fix kostet nichts —
mit `feas_lambda=5e4, feas_w_ptet=100` ist das Ergebnis sogar **besser** (−4,94 % vs. −4,88 %)
bei 0 PTET-Verstößen. Es gibt kein km-Argument für den Default-off.

### P1-5 · As-played-Datenbasis trägt die Beweislast nicht (bekannt, aber unterschätzt)
Einzige Referenzpläne sind as-played (Makeups/Relokationen/Intl). Folgen: (a) die 2025-Baseline
besteht die eigenen harten Checks nicht (SCHED-162: 160–165 Spiele/Team) — der Optimierer
startet von einem formal regelwidrigen Plan; (b) alle „0 Verstöße"-Messungen der
Startzeit-/Strukturregeln sind auf Daten gemessen, in denen Reschedules (die von V(C)(8)/(9)
ausgenommen sind) nicht von Originalplan-Spielen unterscheidbar sind; (c) V(C)(13)/(14) sind
auf dieser Basis prinzipiell nicht hart messbar. Ohne **originale published Schedules**
(MLB veröffentlicht sie ~Juli des Vorjahres; Wayback/MLB-Pressemitteilungen) bleibt jede
Originalplan-Aussage indirekt.

### P1-6 · Green-field ist Forschungsprototyp, kein Produktpfad
Empirisch validiert: monolithic/bnp/rounds/windowed bei n=3–4 Teams, Sekundenbereich.
**n=6 scheitert bereits** an der Restricted License (selbst gemessen); mit Lizenz ist
Voll-Saison-TTP (n=30, 2430 Spiele, tagesindiziert) nach eigener Doku „TTP-hart" — der
ehrliche eigene Befund („reines per-Team-CG verbessert strukturell nicht über Bootstrap")
bestätigt, dass der Skalierungsweg offen ist. Zudem erzwingt der Green-field-MIP nur
B3-Format + V(C)(12) + Roadtrip-Limit — die gesamte restliche harte Regelschicht
(V(C)(11), (13), (14)/(15), Envelope, Startzeiten) ist dort noch gar nicht modelliert.
„FORK 2 = Produktziel" ist Stand heute eine Hypothese.

### P2-7 · Regellücken gegenüber Article V (vollständig durchgesehen)
- **V(C)(5)** (kein Start nach 17:00, wenn ein Club am Folgetag Day-DH spielt): nicht modelliert;
  als Datengrenze dokumentiert — korrekt, aber im Startzeit-Zuweiser (`assign_start_times`)
  wäre sie durchsetzbar und fehlt.
- **V(C)(8)** Unter-Abdeckung: Bedingung „visiting Club travels to a **home off-day**" wird nur
  erfasst, wenn der Gast am Folgetag spielt (start_times.py:166 ff.). Der Kommentar behauptet,
  das „lockere nur" — das ist verkehrt herum: zusätzliche Reise-Clubs können die bindende
  Inflight-Zeit nur **erhöhen**, die Grenze also verschärfen → echte Verstöße können unentdeckt
  bleiben.
- **V(C)(11) Satz 2** (max. 1 Spiel in ET am Tag nach PT-Spiel): nicht separat modelliert;
  durch den konservativen Strikt-Default abgedeckt, **aber nur wenn das PTET-Gate aktiv ist**
  (siehe P0-1) bzw. im Compliance-Report.
- **V(C)(14)** „one home split doubleheader per Club": als nicht prüfbar dokumentiert (DH-Typ
  fehlt im Loader) — MLB-Stats-API liefert `doubleHeader`-Typ (S/Y) aber; die Lücke ist
  schließbar, nicht fundamental.
- **VENUE-AVAIL** ist hart klassifiziert, aber opt-in (`check_venue=False` Default) und
  `tools/backtest.py` übergibt **keine** `home_blackout_days` — im Produktionslauf ungeschützt
  (Risiko derzeit klein: 40 Events in `local_events.json`, Provenienz Recherche-Doc).

### P2-8 · Test-Suite: grün, aber mit blinden Flecken
438 Tests bestehen — aber: (a) der einzige End-to-End-Guard testet die Nicht-Default-Konfiguration
(P0-1); (b) kein Test lässt Compliance auf produktionsidentischem Warm-Start-Output laufen;
(c) kein Test prüft Disruption-Output gegen V(C)(12) (P0-3); (d) 50 `slow`-Tests (CP-SAT-
Vollgenerierung, HAP-Solver, Pareto-Budget) laufen im Standard-Durchlauf nicht — gerade die
Pfade mit den stärksten Garantien-Behauptungen; (e) viele Tests prüfen Toy-Instanzen (2–4 Teams).
Die Suite misst Implementierungs-, nicht Produkt-Korrektheit.

### P3-9 · Kleinigkeiten
- `detect_all_star_break`: heuristisch (längste Lücke im mittleren Drittel) — bei
  Disruption-Szenarien mit langen liga-weiten Lücken fragil; V(C)(17) („four days") wird nicht
  gegen die erkannte Länge validiert.
- `compliance.py`-Kopftabelle (Z. 12–23) ist veraltet: listet AC-2.1.8 als „hard", real ist
  `severity="soft"` — Doku-Drift im selben File.
- Ops-Suite (Hotels/Routing/Security) rechnet auf 5-Team-Seed-Daten — als Demo ok, jede
  Output-Zahl daraus ist aber Illustration, nicht Information.
- pyflakes-Findings in `src/` (unused imports) — kosmetisch.

---

## 3 — Was als Nächstes zu tun ist (geordnet)

1. **Hard-Rule-Gate vor jeden Output** (1–2 Tage): Eine einzige Funktion
   `assert_publishable(season, …)` = `compliance_report(...).is_compliant` +
   `original_schedule_violations(...) == []`, aufgerufen am Ende von `optimize_travel`-Aufrufern
   (backtest, main, whatif, disruption). Output, der sie nicht besteht, wird nicht als Ergebnis
   ausgewiesen (oder klar als „nicht publizierbar" markiert). Damit kann der Fehlerklasse aus
   P0-1/-2/-3 nie wieder still passieren.
2. **PTET-/Feasibility-Gate im Produktionspfad aktivieren** (Stunden): `feas_lambda>0,
   feas_w_ptet>0` als neuen Default in `improve_real_plan`/`main`; alte Defaults hinter
   `--legacy-bitident` legen. Messen, README-Zahlen neu erzeugen. (Meine Messung: kostet keine km.)
3. **V(C)(13)-Penalty/Move-Filter in die SA** (1–2 Tage): Open-Day-Fenster-Zähler inkrementell
   (analog Holiday-Countern) oder Move-Reject bei Fensterverletzung; danach Property-Test auf
   **Produktions-Default** umstellen (P0-1-Testlücke schließen).
4. **V(C)(12)-Bedingungen in alle Repair-Strategien** (1 Tag): Slot-Finder zusätzlich gegen
   20/24-Limits beider Teams prüfen (+ „same series / end of series"-Präferenz); Orchestrator
   meldet `all_teams_pass_fatigue_constraints` im Score-Bundle.
5. **README/Doku-Korrektur** (Stunden): „0 Verletzungen" entfernen oder an Schritte 1–3 knüpfen;
   compliance.py-Kopftabelle aktualisieren. Falsche Headline ist schlimmer als fehlendes Feature.
6. **Original-Schedules 2024/2025 beschaffen** (extern, parallel): published Original-Pläne
   (MLB-Press-Release/Wayback). Erst damit sind V(C)(13)/(14)-Messungen und die 2025-Baseline
   beweiskräftig; löst auch `finding-as-played-data`.
7. **Gurobi-Key** (extern, blockiert P1-6): danach ehrliche Skalierungstreppe messen
   (n=6, 8, 10 … wo bricht rounds/windowed wirklich?) statt Toy-Validierung.
8. **V(C)(14)-Split-DH-Typ in den Loader** (Stunden): `doubleHeader`-Feld der Stats-API erhalten.

---

## 4 — Wie das Produkt besser wird

- **Ein Abnahme-Artefakt pro Lauf:** Jeder Optimierer-/Repair-Lauf endet mit dem
  Compliance-Report (JSON+MD) des **Outputs** neben den km-Zahlen — „messen statt behaupten"
  konsequent auf den eigenen Output angewandt. Aktuell wird genau dort nicht gemessen.
- **Zwei Betriebsmodi explizit machen:** „Forschung" (Gates frei) vs. „Publizierbar"
  (alle harten Regeln erzwungen, Gate-Check verpflichtend). Ein MLB-Nutzer sieht nur Modus 2.
- **SA-Moves regelbewusst statt regelblind:** Die Architektur hat bereits inkrementelle
  Counter (km, Fatigue, Holiday) — dasselbe Muster für Open-Day-Fenster und PT→ET macht die
  harten Regeln zu Move-Invarianten statt Hoffnungswerten.
- **Startzeiten in den Optimierungspfad ziehen:** Die 5.1-Schicht ist reine Validierung.
  Produktwert entsteht, wenn `assign_start_times` + TV-Pins Teil des Outputs sind und V(C)(5)
  gleich mit erzwungen wird (Daten dafür sind da: Appendix C ✓).
- **Benchmark gegen die Literatur:** TTP-/MLB-Scheduling hat publizierte Referenzen (z. B.
  Trick/Easton-Arbeiten, Gurobi-MLB-Case-Studies). Eine Einordnung „unsere −4,9 % vs. was
  state-of-the-art auf realen MLB-Instanzen erreicht" würde die Aussagekraft der Zahl massiv
  erhöhen — derzeit fehlt jeder externe Vergleichspunkt.
- **CI-Lauf für die `slow`-Suite** (nightly), damit die stärksten Garantien nicht nur auf
  Entwickler-Disziplin beruhen.

---

## 5 — Risiken / blinde Flecken

1. **CBA-Horizont:** Das Basic Agreement 2022–2026 läuft am 1. Dez 2026 aus. Alle Verbatim-Regeln
   können sich ändern (Lockout-Risiko ist real). Regel-IDs/Quellen sind sauber zentralisiert —
   gut —, aber es gibt keinen „CBA-Versionsschalter" im Datenmodell.
2. **Nicht-modellierte Realität:** Die Liga plant mit Constraints, die im Modell fehlen —
   Sunday-Night-Rotation (V(C)(17) Satz 2, mehrjährig), internationale Serien (werden als
   neutral ausgefiltert statt geplant), Rivalry-/Interleague-Konventionen, Broadcaster-Verträge
   pro Club, Stadion-Co-Tenants (C3 offen). Ein realer Scheduler merkt das in der ersten Stunde.
3. **Selbstbestätigungs-Schleife bei Schwellen:** Der Feasibility-Envelope (4200 km/3 Hops) ist
   aus genau den zwei Saisons kalibriert, gegen die er gemessen wird — er kann reale
   Planungsgrenzen (Charter-Verfügbarkeit, Einreise Kanada) nur abbilden, soweit sie 2024/25
   zufällig sichtbar wurden.
4. **Einzelne Datenquelle:** Alles hängt an `mlb_schedule_{2024,2025}.json` einer API-Abfrage.
   Kein Hash/Freeze-Manifest, kein zweiter Provider-Abgleich — stiller Datendrift wäre unsichtbar.
5. **Komplexitäts-Risiko:** 51 Module, viele Analyse-Schichten (Chrono, Pareto, Ops, What-if) um
   einen Kern, dessen Hauptversprechen aktuell nicht hält. Die Breite täuscht Reife vor —
   Priorität sollte die Härtung des Kerns sein, nicht weitere Schichten.
6. **Mein Review-Blindfleck:** `slow`-Suite und Voll-Backtests mit Original-`tools/backtest.py`
   (inkl. Report-Generierung) habe ich aus Zeitgründen nicht vollständig laufen lassen; Gurobi
   nur Restricted. Die P0-Befunde sind davon unabhängig belegt.

---

## 6 — Reproduktion der Kernbefunde

```bash
export PYTHONPATH="$(pwd)"

# P0-1/P0-2: Produktions-Default erzeugt harte Verstöße
python3 - <<'EOF'
from src.data_loader import load_teams, teams_by_id as tbi
from src.datasources.local_file import LocalFileAdapter
from src.season import detect_all_star_break
from src.generator_optimizer import GeneratorConfig, OptimizerConfig, optimize_travel
from src.compliance import compliance_report
from src.schedule_rules import check_offday_distribution
teams = load_teams(); tb = tbi(teams)
real = LocalFileAdapter(base_dir="data").fetch_season_schedule(2024)
cfg = GeneratorConfig(season=2024, season_start=real.season_start, season_end=real.season_end,
                      all_star_break=detect_all_star_break(real), num_search_workers=1,
                      random_seed=42, enforce_fatigue_constraints=True)
oc = OptimizerConfig(iterations=6_000_000, move_mix_geo=0.35, seed=42, fatigue_lambda=1e6)
out, log = optimize_travel(real, teams, cfg, oc)
rep = compliance_report(out, teams_by_id=tb)
print("hard failures:", [c.rule_id for c in rep.hard_failures])      # ['CBA-PTET']
print(rep.get("CBA-PTET").measured)                                   # 18 Verstöße
base = {(v.team, v.detail) for v in check_offday_distribution(real)}
new  = {(v.team, v.detail) for v in check_offday_distribution(out)} - base
print("neue V(C)(13)-Verstöße:", len(new))                            # 36
EOF

# P0-3: repair_local verletzt V(C)(12)
python3 - <<'EOF'
from datetime import date
from src.datasources.local_file import LocalFileAdapter
from src.disruption_types import StadiumBlackout
from src.repair_local import repair_local
from src.player_fatigue import max_games_without_off_day
real = LocalFileAdapter(base_dir="data").fetch_season_schedule(2024)
bl = StadiumBlackout(home_team="NYY", start_date=date(2024,8,5), end_date=date(2024,8,18))
new, _, _ = repair_local(real, bl)
print(max_games_without_off_day(new, "NYY"))                          # 25 (Limit 20/24)
EOF

# P1-6: Green-field-Größenlimit
python -m tools.greenfield_demo --method rounds --teams NYY,BOS,TBR,TOR,BAL,CLE --games-per-pair 2
# → "Model too large for size-limited license"
```

*Messumgebung: Sandbox-Linux, Python 3.10, ortools 9.10.4067, gurobipy Restricted.
SA-Laufzeit 6 M Iterationen ≈ 28 s.*

---

# ADDENDUM — Remediation (gleiche Session, 2026-06-10)

Alle P0-Befunde wurden behoben und **mit denselben Repro-Skripten nachgemessen**
(„beweisen statt behaupten"). Suite: **441/441 nicht-slow grün** (438 alte + 3 neue);
Determinismus erhalten (Produktions-Config 2× bit-identisch; Legacy-Pfad bit-identisch
zur Vor-Fix-Messung: 200 k/Seed 42 → final_km 1680131 exakt reproduziert).

| Befund | Status | Beweis (vorher → nachher, identisches Repro-Skript) |
|---|---|---|
| **P0-1** SA-Default erzeugt harte Verstöße | **behoben** | Warm-Start 2024, 3 M Iter: vorher `hard=['CBA-PTET']` (18×), 2025 zusätzl. FEAS-GETA (28×) → nachher `hard=[]`, PTET=0, Gate **PASS** (beide Saisons). Produktions-Default = `production_optimizer_config()` (feas/ptet/sched13 aktiv); Alt-Verhalten nur noch `--legacy-bitident` (Output wird markiert). |
| **P0-2** V(C)(13)-Guard nie aufgerufen | **behoben** | Neues `src/publish_gate.py`, verdrahtet in backtest/main/whatif. SA: baseline-relativer V(C)(13)-Term in Checker-Granularität + **Best-Filter** (Best-Lösung nur aus Zuständen ohne neue Verstöße). Vorher 36 neue V(C)(13)-Team-Verstöße → nachher **0 Team-Kategorien über Baseline** (Gate PASS; geerbte Artefakt-Fenster können innerhalb eines Teams wandern, Anzahl je Kategorie steigt nie). Property-Test testet jetzt den **Produktions-Default** (test_optimizer_introduces_no_new_hard_violation, grün) + Regressionstest `test_production_default_is_gated_config`. |
| **P0-3** repair_local bricht V(C)(12) | **behoben** | NYY-Blackout-Repro: vorher 25-Tage-Streak → nachher 17, `all_teams_pass_fatigue_constraints` ok; zweistufiger Slot-Finder (≤20, Fallback ≤24 = CBA-Reschedule-Grenze, im Change-Note dokumentiert); nicht konform platzierbare Spiele → ehrlich `unreschedulable` (3→4). Orchestrator zählt jetzt NEUE Fatigue-Verstöße in `hard_constraint_violations`. 2 neue Tests. |
| **P1-4** Bit-Identität schlug Regelkorrektheit | **behoben** | Schutzterme sind Produktions-Default; Dataclass-Default bleibt 0 (Test-Kontrakt), Produktionspfade nutzen `production_optimizer_config()`. **Ehrlicher Trade-off gemessen:** volle Konformität kostet km — 2024 −2,4 % statt −4,9 % (3 M Iter); die alte Zahl war nicht publizierbar. README korrigiert. |
| **P1-5** as-played-Datenbasis | **extern blockiert** | Original-published Schedules beschaffen (MLB-Press-Releases/Wayback). Gate arbeitet deshalb baseline-relativ und weist geerbte Artefakte getrennt aus. |
| **P1-6** Green-field Forschungsstadium | **extern blockiert** | Gurobi-Key (`.env`) nötig; ohne Lizenz scheitert n=6 am Größenlimit (gemessen). Code-seitig unverändert offen: restliche harte Regelschicht im MIP. |
| **P2-7** Regellücken (V(C)(5), V(C)(8)-Heim-Off-Day, Split-DH) | **offen** | Nicht Teil dieses Fix-Pakets; unverändert dokumentiert. |
| **P3-9** compliance.py-Kopftabelle veraltet / README-Claim falsch | **behoben** | Tabelle vollständig + AC-2.1.8 korrekt als soft; README-Claim ersetzt durch gemessene, Gate-konforme Zahlen inkl. Hinweis auf den früheren Fehler. |

**Neue/geänderte Artefakte:** `src/publish_gate.py` (neu), `src/generator_optimizer.py`
(sched13-Term, Best-Filter, `production_optimizer_config`), `tools/backtest.py` (Gate +
`--legacy-bitident`/`--allow-unpublishable`), `src/main.py` (aktive CLI-Defaults, Gate,
Exit 1 bei Gate-Bruch, Gate-Feld im JSON-Export), `src/whatif_core/*` (Gate-Warnung),
`src/repair_local.py` (V(C)(12)-Slot-Finder), `src/disruption.py` (Verstoß-Zählung),
Tests (Property-Test auf Produktions-Default, 3 neue Tests), README, compliance.py-Doku.

**Bekannte Restpunkte (ehrlich):** (a) km-Ersparnis unter voller Konformität ist
niedriger (−2,4 %/−1,9 % bei 3 M Iter; 6 M im Sandbox-Limit nicht messbar — auf
Jonas' Rechner nachmessen); (b) geerbte V(C)(13)-Artefakt-Fenster können innerhalb
eines Teams die Position wechseln (Anzahl je Kategorie steigt nie); (c) `tools/api.py`
und der Pareto-Pfad sind noch nicht ans Gate angeschlossen (Backlog).

---

# ADDENDUM 2 — Remediation Runde 2 (2026-06-10/11)

Restpunkte + selbst aufgedeckte Lücken geschlossen; jeder Punkt nachgemessen.
Suite: **443/443 nicht-slow grün** (441 + 2 neue); Determinismus erhalten
(Legacy 200 k/Seed 42 → final_km **1680131** exakt; Produktions-Config 2× bit-identisch).

| Punkt | Status | Beweis |
|---|---|---|
| **0 — Gate-Abdeckung api/pareto + Aufrufer-Audit** | **behoben** | Aufrufer-Inventar per grep dokumentiert. `tools/api.py`: `/schedule/generate` + `/schedule/pareto` liefern `publishable` + `publish_gate` je Antwort/Punkt; `sample_pareto_frontier` gated jeden Frontier-Punkt (gemessen: Punkte tragen Gate-Felder); Disruption-Orchestrator nutzt das VOLLE Gate je Alternative (`hard_constraint_violations` = unverlegbar + neue harte/strukturelle Verstöße; Perf-AC ≤60 s weiter erfüllt: 5,5 s). Forschungs-Instrumente (build_calibration/tuning/diagnose_e2) explizit als Nicht-Output-Pfade markiert. Pareto-SA selbst bleibt regel-blind → Punkte werden MARKIERT (ehrlich sichtbar), nicht verworfen. |
| **0b — schwächere Garantie messen + benennen** | **behoben** | Messung 2024/2025 (3 M Iter, (Team, Regel, Kategorie)-Granularität): **ERHÖHT = {} (leer)** in beiden Saisons; 2024: 1 Kategorie gesunken, 11 unverändert; 2025: 4 gesunken, 8 unverändert. Gate-Summary + Modul-Doku sagen jetzt wörtlich: „Garantie: keine Verstoß-Kategorie je Team über Baseline (NICHT '0 Verstöße')". |
| **1 — V(C)(14) Split-DH** | **behoben** | `Game.dh_type` (S/Y) im Loader erhalten (Daten vorhanden: 2024 N=2408/Y=30/S=31); „one home split-DH per Club"-Check aktiv. Gemessen as-played: 2024 4 Clubs, 2025 7 Clubs über Limit 1 = Makeup-Artefakte (informativ). 2 neue Tests. DATENGRENZE dokumentiert: SA-Output rekonstruiert Spiele ohne dh_type → Teilcheck dort vakuos. |
| **2 — VENUE-AVAIL in Produktion** | **behoben** | backtest + main übergeben `home_blackout_days` (aus `local_events.json`) an die SA und `events` ans Gate. Ehrlicher Befund: Event-Daten decken nur 2026 ab → für 2024/2025-Backtests binden 0 Tage (Struktur steht, Daten-Item C3 bleibt extern). |
| **3 — Startzeiten im Output + V(C)(5)** | **behoben** | `main.py` exportiert je Spiel `start_local`/`slot` + `start_time_rules` (gemessen: GETAWAY/NIGHTDAY/DAYDH/DAYMIN = OK auf 2432 Spielen). Neue Regel `STARTTIME-DAYDH` (V(C)(5), hart, gegated) + Durchsetzung im Zuweiser (17:00-Cap; DH-Politik Day-Night, V(C)(8)-Cap auch für DH-Spiele). Gemessen real: roh 5/5 Treffer = ausnahmslos Makeup-Artefakte (0/0 ohne Reschedules); zugewiesen: V(C)(5)/(6)/(8)/(9) = 0/0/0/0, deterministisch. |
| **4 — V(C)(8)-Heim-Off-Day-Lücke** | **behoben** | `find_getaway_contexts` erfasst jetzt „visiting Club travels to a home off-day"; falscher Kommentar korrigiert (zusätzliche Reise-Clubs VERSCHÄRFEN die Grenze). Beweis, dass die Lücke real war: volle Abdeckung findet je 1 Roh-Treffer 2024/2025 — exakt die CBA-Ausnahmen (LAD@NYY Sunday Night 2024-06-09; SDP@PHI Makeup 2025-07-02). Mit Ausnahme-Mengen (`load_exempt_pks`: Reschedules faktisch, SNB als dokumentierte Heuristik): **0 Verstöße**. Tests + RUNBOOK aktualisiert. |
| **5 — V(C)(11) Satz 2** | **belegt (subsumiert)** | Messung: 0 PT→ET-Folgetag-Transitionen in beiden realen Saisons → 0 Satz-2-Fälle. Subsumtions-Test (`test_ptet_strict_check_subsumes_vc11_sentence2`): PT-Spiel → ET-DH am Folgetag wird vom strikten CBA-PTET-Check geflaggt. Kein separates Modell nötig, solange der strikte Default gilt (≤7-Ausnahme nicht modelliert — dokumentiert). |
| **6 — Betriebsmodi + Report je Lauf** | **behoben** | `--mode publizierbar\|forschung` in main + backtest; `src/run_report.py` schreibt `<label>_compliance.{json,md}` neben jeden Plan-Export (verifiziert: Artefakte erzeugt, MD enthält Gate-Garantie-Hinweis + volle Regeltabelle). |
| **7 — Nightly-CI für slow-Tests** | **behoben (Infra)** | `.github/workflows/tests.yml`: slow-Suite nightly (Cron 03:00) + `workflow_dispatch` statt unrealistischem 25-min-Push-Job; Manifest-Check + Lint integriert; lokaler Runner `tools/run_slow_suite.sh`. Stichproben bestanden (Property-Test Produktions-Default 2,9 s; repair_regenerate-slow 4,2 s; Orchestrator-Perf-AC 5,5 s). EHRLICH: Milton-e2e (slow) überschreitet das 43-s-Sandbox-Fenster → erst der nightly Lauf führt ihn wieder regelmäßig aus. |
| **8 — Daten-Manifest** | **behoben** | `data/MANIFEST.sha256.json` (Schedules, teams, Appendix C) + `tools/verify_data_manifest.py` (--update nach bewusstem Update) + automatischer Drift-Check im LocalFileAdapter (Warnung, einmal je Datei, Opt-out `MLB_SKIP_MANIFEST=1`). Beweis: manipulierte Kopie → DRIFT-Warnung; Original → 4× OK. |
| **9 — ASB-Validierung + Lint** | **behoben** | Neue Soft-Regel `CBA-ASB` (V(C)(17): erkannte ASB-Länge = 4 Tage; gemessen 2024/2025: exakt 4). `src/` pyflakes-clean (0 Findings ohne legacy); `TIMEZONE_OFFSET`-Re-Export bewahrt (Cleanup hatte ihn kurz zerlegt — vom Test-Suite-Lauf gefangen, zurückgenommen, als Re-Export markiert); ops_hotels-Tabelle zeigt die berechnete (vorher nie angezeigte) Rate. |

**Bewusst offen (extern/Design):** Original-Schedules (P1-5), Gurobi-Key (P1-6),
Literatur-Benchmark, CBA-Versionsschalter (Design-Vorschlag ausstehend).
**Neue Restpunkte (ehrlich):** SNB-Erkennung ist Heuristik (Broadcaster-Daten = C2);
`dh_type` überlebt den SA-Roundtrip nicht (V(C)(14)-Satz-2 auf SA-Output vakuos);
Pareto-SA regel-blind (Punkte nur markiert); Milton-e2e nur via nightly CI messbar.
