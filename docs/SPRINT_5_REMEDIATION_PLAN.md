# Sprint 5 — Maßnahmenplan A–G (Gap-Register → MLB-ready)

**Stand:** 2026-06-09. Dieser Plan macht aus dem `SPRINT_5_GAP_REGISTER.md` einen
konkreten, sequenzierten Umsetzungsplan: *wie* jede Lücke geschlossen wird,
*womit* sie als erledigt gilt (Akzeptanzkriterium), *wie aufwändig*, *wovon abhängig*.
**Noch Planungsphase — es wird hier nichts gebaut.** Erst wenn dieser Plan steht und
die zwei Design-Forks (§ 1) entschieden sind, beginnt die Umsetzung.

Querverweise: `SPRINT_5_GAP_REGISTER.md` (Befunde), `SPRINT_5_DATA_FINDINGS.md`
(Daten), `SPRINT_5_RESEARCH_METHODOLOGY.md` (Methode), `regulations/` (CBA verbatim).

---

## 0 — Verbindliche Prinzipien (für jede Maßnahme)

- **Messen statt behaupten:** Jede Maßnahme endet mit einer Messung gegen den **realen
  2024- UND 2025-Plan** (nicht 2026-generiert) — schließt GAP-G1.
- **Determinismus:** neue Constraints/Terme gegated (Default off → bit-identisch), bis
  bewusst aktiviert. Keine externe Nicht-Determinismus-Quelle im Kernpfad (GAP-E1).
- **Daten-Ehrlichkeit:** echt vs. Proxy vs. Seed klar markiert; jede Datenzeile mit
  Quelle + Admiralty-Rating (GAP-G2, diesmal konsequent).
- **Compliance-Wahrheit:** „hard" nur, was real bindend ist (kein Heuristik-als-hart).

---

## 1 — Zwei Design-Forks — ENTSCHIEDEN (2026-06-09, Jonas)

Beide Forks wurden auf die **ambitionierte Option B** entschieden. Das erweitert den
Scope erheblich (mehrwöchig), liefert aber das vollständige MLB-Niveau.

### FORK 1 — Startzeiten modellieren? → **JA (Option B)**
Startzeit wird eine **Modell-Dimension**: jede Serie/jedes Spiel bekommt einen
Zeit-Slot (Day ~13:00 / Night ~19:00 / Getaway-früh / TV-fixiert). Konsequenzen:
- **V(C)(8)** (Getaway-Startzeit-Formel) und **V(C)(9)** (Tag-nach-Nacht ≥17:00) werden
  **hart durchsetzbar** → GAP-A3 wird gebaut, nicht out-of-scope erklärt.
- **V(C)(6)/(7)** (Day-Game-Startzeit-Untergrenzen) ebenfalls modellierbar.
- **Hartes TV-WINDOW wird sinnvoll** (GAP-G3 umgekehrt): nationale Fenster lassen sich
  an Startzeit-Slots binden (Apple-Freitag, ESPN-Sonntag-19:00). TV ist nicht mehr nur
  weiches Scoring.
- **Abhängigkeit:** V(C)(8) braucht die **echten Appendix-C-Reisezeiten** → GAP-C4 wird
  Hart-Voraussetzung (offizielles Bild beschaffen + transkribieren).
- **Architektur:** SA/CP-SAT muss Zeit-Slots mit zuweisen/respektieren. Das ist die
  größte Einzeländerung in Sprint 5 → eigener Fundament-Block (5.1).

### FORK 2 — Echtes From-Scratch / green-field? → **JA (Option B)**
Green-field-Scheduling wird Produktziel. Konsequenzen:
- **Branch-and-Price / Gurobi** kommt zurück auf den Pflicht-Pfad — **aber für die
  *echten* harten Regeln** (AC-2.1.9/20, Serienstruktur, Startzeit-Regeln), **nicht**
  für die ≤13-Heuristik (die bleibt weich, AC-2.1.8-Entscheidung gilt).
- **GAP-B3** wird Pflicht: Balanced-Schedule-Format (seit 2023) als strukturelle
  Constraints (Matchup-Matrix: wer spielt wie oft gegen wen) — sonst erzeugt
  From-Scratch keinen formal gültigen MLB-Plan.
- **Enabler:** Gurobi Academic License (Jonas, übers Uni-WLAN) — für den
  Tractability-Durchbruch, an dem die CP-SAT-Standardmittel (Q10) scheiterten.
- **Akzeptanz:** From-Scratch erzeugt **zuverlässig** einen voll CBA-konformen Plan
  (alle harten Regeln, mehrere Seeds, akzeptable Zeit) → dann ist „nicht MLB-tauglich"
  aufgehoben.

> **Ehrliche Einordnung:** Beide B-Optionen zusammen machen aus Sprint 5 ein
> **mehrwöchiges, mehrblockiges** Unterfangen mit echtem Forschungsanteil (Startzeit-
> Modellierung + Branch-and-Price). Das ist machbar und auf MLB-Niveau lohnend, aber
> kein „in einer Sitzung gebaut". Wir gehen es blockweise an, jeder Block mit Messung.

---

## A — CBA-Compliance-Vollständigkeit (Kernkorrektheit)

**Ziel:** Der Compliance-Report prüft *alle* realen harten Article-V-Regeln, nicht 7
von ~12. Jede Regel ↔ Verbatim-Zitat aus `regulations/CBA_2022-2026_Article_V_Scheduling.md`.

| Gap | Ansatz | Akzeptanzkriterium | Aufwand |
|---|---|---|---|
| **A1 — V(C)(11) PT→ET-Off-Day** | Neuer harter Check `_check_pt_et_offday` in `compliance.py`; nutzt `timezones.py`. Für jede Folge PT-Stadt → ET-Stadt ohne Off-Day = Verstoß (max. 7 Liga-Ausnahmen abbilden). Zusätzlich gegateter SA-Penalty, damit Moves es nicht brechen. | Realer 2024+2025-Plan compliant; SA führt keine neuen Verstöße ein (Messung) | Mittel |
| **A2 — V(C)(13) Off-Day-Verteilung** | `_check_offday_distribution`: ≤2 Open Days je 7-Tage-Fenster; ≥7 in letzten 67 Tagen; ≥3 in letzten 32. | Gegen realen Plan validiert; als hart eingestuft | Mittel |
| **A3 — V(C)(8)/(9) Startzeiten** | Abhängig von **FORK 1**. Option A: als out-of-scope dokumentieren (Scope-Statement im README + compliance-Doku). Option B: Startzeit-Dimension + Checks. | Scope explizit ODER Checks implementiert | klein (A) / hoch (B) |
| **A4 — V(C)(14)/(15) Doubleheader-Limits** | `_check_doubleheader_limits`: keine DH an Folgetagen im Originalplan; Twi-Night ≤3/Heimclub; nicht am Getaway. | Gegen realen Plan validiert | klein-mittel |

**Querschnitt:** Nach A1–A4 muss der **SA-Move-Set eine Post-Move-Validierung** gegen
*alle* harten Regeln bekommen (schließt die „stille Verletzung"-Gefahr aus dem
Gap-Register). Akzeptanz: Property-Test „kein akzeptierter Move erzeugt einen harten
Verstoß".

---

## B — Modell-Scope (ehrliche Grenzen ziehen)

| Gap | Ansatz | Akzeptanzkriterium |
|---|---|---|
| **B1** | FORK 1. Option A: präzises **Scope-Statement** („Optimierer ist tag-granular; Startzeiten nachgelagert") in README + ARCHITECTURE_DECISION. | Scope dokumentiert, keine versteckte Lücke mehr |
| **B2** | FORK 2. Option A: From-Scratch bleibt explizit „validation-only"; Doku schärfen. | Klare Produkt-Scope-Aussage |
| **B3** | Nur bei FORK 2 = B relevant: Balanced-Schedule-Format als strukturelle Constraints. Sonst: dokumentieren, dass Warm-Start das Format erbt. | dokumentiert / implementiert |
| **B4** | Makeup/Rainout/Postseason explizit als out-of-scope (separate Ops-Funktion) deklarieren. | Scope-Statement |

---

## C — Datenrealismus (echt machen oder ehrlich als Proxy markieren)

| Gap | Ansatz | Akzeptanzkriterium | Aufwand |
|---|---|---|---|
| **C1 — Gate-Receipts** | Forbes-Jahres-Gate als Skalen-Kalibrierung + **Sensitivitätsanalyse** (±20 % Preis → ändert sich die Optimierungsentscheidung?). Bleibt klar markierter Proxy. | Proxy kalibriert + Sensitivität dokumentiert | Mittel |
| **C2 — TV pro Spiel** | `tv_slots.json` mit verifizierten nationalen Fenstern 2024/2025 anreichern (SMW × Schedule-JSON-Join). **Bleibt weich** (kein hartes TV-WINDOW — s. GAP-G3). | ≥95 % Fenster validiert, je gegen JSON gejoint | Mittel (Fleiß) |
| **C3 — Venue** | Harte geteilte-Venue-Konflikte 2025 exakt aus Co-Tenant-Plänen (River Cats/Tarpons) → `event_conflicts`/`home_blackout_days`. Standard-Stadien: Konzerte best-effort + Coverage-Hinweis. | Geteilte Venues exakt; Coverage dokumentiert | Mittel-hoch |
| **C4 — Appendix C** | Offizielles Bild in `regulations/` (Jonas lädt es), dann in Reisezeit-Matrix transkribieren; bis dahin an 2 Ankern kalibrierter Proxy. | Matrix aus offizieller Quelle ODER Proxy ≤5 % auf Ankern | klein-mittel |
| **C5 — Ops-Seeds** | In Sprint-5.3 (Ops-Suite) via Club-Import echtes Schema befüllen; Seeds markiert lassen. | Import-Pfad steht | (in 5.3) |
| **C6 — Revenue-Kalibrierung** | **Zuerst klären:** was nutzt `revenue_model.json` real (Sportico? Attendance? Spearman 0,89)? Eine kanonische Quelle festlegen + dokumentieren. | Eindeutige, dokumentierte Kalibrierungs-Basis | klein |

---

## D — Wissenschaftliche Fundierung (Fatigue evidenzbasiert)

| Gap | Ansatz | Akzeptanzkriterium |
|---|---|---|
| **D1** | Chronobiologie-Effekte aus 1992–2011 **konservativ diskontieren** (moderne Charter-/Ruheregeln); wo möglich neuere Studien ergänzen. | Gewichte mit Quelle + Diskont-Begründung |
| **D2** | Mapping „Performance-Effekt → Strafgewicht" **explizit** als Annahme dokumentieren; konservativ wählen; Sensitivität testen. | Mapping offengelegt + getestet |
| **D3** | Fatigue-Gewichte **symmetrisch/neutral** anwenden (kein Wettbewerbsvorteil); Fairness-Prinzip dokumentieren. | Fairness-Statement + Test |

---

## E — Determinismus vs. Integration

| Gap | Ansatz | Akzeptanzkriterium |
|---|---|---|
| **E1 — Routing** | ORS → **eingefrorener, versionierter Cache** → Haversine-Fallback. Default deterministisch. | Cache reproduzierbar; Fallback ohne Key funktioniert |
| **E2 — 2025 schwächer** | **Diagnose** (warum −2,6 % vs. −5,4 %?): Venue-Sonderfälle 2025? Datenqualität? Tuning? Erst messen, dann erklären. | Ursache belegt + dokumentiert |

---

## F — AC-2.1.8-Aufräumen (zuerst, billig, hoher Hebel)

| Gap | Ansatz | Akzeptanzkriterium |
|---|---|---|
| **F1** | `compliance.py`: AC-2.1.8 `severity` „hard" → **„soft"**. | Compliance stuft 13-Regel als weich ein |
| **F2** | xfail-Test `test_AC_2_1_8_...` auf **weiches Qualitätsziel** umstellen (Roadtrip-Länge minimieren, keine ≤13-Pflicht). | Test grün/umgewidmet, kein xfail-Schuldschein |
| **F3** | 5.4/Q10: Branch-and-Price aus der Pflichtliste; Q10 als „gelöst durch Re-Klassifikation" schließen. | Q10 geschlossen dokumentiert |
| **F4** | Doku-Sweep: `REFACTOR_BACKLOG` (Q10), `CBA_DEFINITIONS`, `README` („AC-2.1.8/9 hard") an neue Einstufung anpassen. | Docs konsistent |

---

## G — Prozess/Methodik (Querschnitt, durchgehend)

- **G1:** Jede A–E-Maßnahme endet mit einer **Messung gegen realen 2024+2025-Plan**.
  Nicht „done", bevor gemessen.
- **G2:** Admiralty-Ratings **konsequent** in jede neue Datendatei (Spalte `source`,
  `rating`).
- **G3:** TV bleibt **weich** (kein hartes TV-WINDOW) — Sprint-5-Plan entsprechend korrigiert.

---

## 2 — Sequenzierung (revidierte Sprint-5-Roadmap)

| Block | Inhalt | Gründe für die Position |
|---|---|---|
| **5.0 — Cleanup** | F1–F4 (AC-2.1.8 → soft, Q10 schließen, Docs) | billig, entlastet sofort; sofort startbar |
| **5.1 — Startzeit-Fundament** 🆕 | Startzeit-Dimension ins Modell (FORK 1); Daten-Voraussetzung Appendix C real (C4) | **größte Architekturänderung**, gated A3/TV — muss früh & stabil stehen |
| **5.2 — Compliance-Vollständigkeit** | A1 (PT→ET), A2 (Off-Day-Verteilung), A3 (Startzeit-Regeln V(C)(8)/(9)), A4 (DH-Limits) + Post-Move-Validierung + Messung | Kernkorrektheit; A3 baut auf 5.1 |
| **5.3 — Daten** | C1 (Gate/Forbes), C2 (TV jetzt *hart*, an Slots gebunden), C3 (Venue), C6 (Revenue-Klärung) + E1 (Routing-Cache) | baut auf Compliance + Startzeit auf |
| **5.4 — Green-field (Branch-and-Price)** 🆕 | FORK 2: B&P/Gurobi für From-Scratch; B3 (Balanced-Schedule-Format); E2-Diagnose | höchstes Risiko/Forschung; braucht Gurobi-Lizenz; zuletzt |
| **5.5 — Ops & Fundierung** | C5 + Ops-Suite (Hotel/Routing/Security); D1–D3 (Fatigue-Evidenz) | Verfeinerung + sichtbarer Ops-Layer |

**Definition of Done (MLB-ready):** alle harten Article-V-Regeln geprüft *und*
durchgesetzt (inkl. Startzeit-Regeln) · Startzeiten modelliert · From-Scratch erzeugt
zuverlässig einen voll konformen Plan · jede Datenart echt oder markierter Proxy mit
Sensitivität · kein Move bricht still eine harte Regel · Compliance-Einstufungen korrekt
· alles gegen 2024+2025 gemessen.

---

## 2b — Umsetzungs-Fortschritt & Befunde (Live-Log)

**5.0 — Cleanup: ✅ ABGESCHLOSSEN (2026-06-09).** F1 (AC-2.1.8→soft), F2 (xfail
umgewidmet), F3/F4 (Q10 geschlossen, Docs-Sweep). Verifiziert: Compliance 21/21,
Fatigue 19/19, Sprint-4+QA 31/31 grün; Determinismus-Default unberührt.

**A1 — V(C)(11) PT→ET-Off-Day: ✅ ABGESCHLOSSEN (2026-06-09).** Neue harte Regel
`CBA-PTET` in `compliance.py` (+ `_check_pt_et_offday`). Konservativ (≤7-Liga-Ausnahme
mit später ET-Startzeit nicht modelliert → strikter Default). **Gemessen:** realer
2024- UND 2025-Plan = **0 PT→ET-Folgen ohne Off-Day** → compliant. 3 neue Tests
(Verstoß / Off-Day-Fall / real-2024), Suite 24/24 grün.

**A2 — V(C)(13) Off-Day-Verteilung: ⚠️ BLOCKIERT durch Datensemantik.** Befund beim
Messen: der reale Plan in `data/mlb_schedule_{2024,2025}.json` ist **„as-played"**
(verschobene Spiele/Makeups, internationale Serien). Die Off-Day-Verteilung darin
weicht von der Originalplan-Regel V(C)(13) ab (Fenster mit 3–4 Off-Tagen, z. B. COL
17.–23.4.2025) — **Rainout-/Reschedule-Artefakte**, keine echten Regelverstöße.
V(C)(13) gilt für den **Originalplan**. → A2 lässt sich gegen die as-played-Daten nicht
sauber validieren. **Braucht:** die original veröffentlichten Schedules (as-scheduled)
ODER eine Entscheidung, A2 nur auf Optimierer-Output (sauber) als Guard zu prüfen.
Siehe auch [[finding-as-played-data]].

**Nebenbefund (relevant für GAP-E2 / SCHED-162/HA):** Der 2025-as-played-Datensatz
streut 160–165 Spiele/Team (CHC 160, CIN 165) und 79–83 Heim — internationale Serien
(Tokyo) + Relokationen (A's Sacramento, Rays Steinbrenner) + Makeups. Mit
`reference_counts` (Selbstreferenz) ist das ok; die nominale ±1-Toleranz greift hier nicht.

**A3 (Startzeit-Regeln) / A4 (DH-Limits):** überwiegend startzeit-abhängig → mit
Block 5.1 (wartet auf das Appendix-C-PNG).

**5.1 — Startzeit-Fundament: ✅ ABGESCHLOSSEN (2026-06-10).** Appendix C transkribiert+
verifiziert (`data/appendix_c_travel_times.json`, 30×30, 0/406 Mismatches, Anker grün).
`src/start_times.py` (gegated, deterministisch): V(C)(8)-Getaway-Formel, Validatoren,
DST-korrekte Echtzeit-Extraktion. 3 Compliance-Regeln STARTTIME-GETAWAY/-NIGHTDAY (hart)
/-DAYMIN (weich), gegated über `start_min`. Gemessen real 2024+2025: V(C)(8) 0, V(C)(9) 0
(mit CBA-Ausnahmen), V(C)(6) nur Früh-Specials. Doku
`regulations/SPRINT_5_1_STARTTIME_MEASUREMENT.md`.

**5.2 — Compliance-Vollständigkeit: ✅ ABGESCHLOSSEN (2026-06-10).** A4
(V(C)(14)/(15) DH-Limits) + A2 (V(C)(13) Off-Day-Verteilung als Guard) + A3-Rest
(V(C)(15) Twi-Night) in `src/schedule_rules.py`, als SOFT-Regeln `CBA-OFFDAY`/`CBA-DH`
verdrahtet (Originalplan-Regeln; auf as-played informativ — V(C)(13): 12/8 Artefakte,
V(C)(14): 2025 4 Makeup-DHs, V(C)(15): 0). **Querschnitt gefunden+gefixt:** der
SA-Optimierer erzeugte einen stillen `CBA-PTET`-Verstoß → neuer gegateter SA-Penalty
`feas_w_ptet` (Default 0 → bit-identisch; CLI `--feas-ptet`); Post-Output-Property-Test
belegt: kein neuer harter Verstoß. V(C)(5) als Datengrenze dokumentiert. Doku
`regulations/SPRINT_5_2_COMPLIANCE_MEASUREMENT.md`. **Damit ist A2 als Guard geschlossen**
(as-played-Limitation bleibt; original-as-scheduled-Beschaffung weiter optional).

---

## 3 — Was ich von Jonas brauche (Forks entschieden → das bleibt offen)

1. **Gurobi Academic License** (übers Uni-WLAN aktivieren) — Enabler für 5.4
   (green-field Branch-and-Price). Erst in 5.4 nötig, nicht eilig.
2. **Appendix-C-Bild** von der True-Blue-LA-Seite herunterladen und in `regulations/`
   ablegen — jetzt **Hart-Voraussetzung** für 5.1/A3 (V(C)(8) braucht echte Reisezeiten).
3. Sonst nichts Blockierendes — 5.0 (Cleanup) ist sofort startbar.

Der Plan ist mit den Fork-Entscheidungen **final**; Umsetzung blockweise 5.0 → 5.5,
jeder Block endet mit Messung gegen 2024+2025.
