# Sprint 3 — Detaillierter Arbeitsplan (zur Abnahme)

**Stand:** 2026-06-01 · **Status:** Plan zur Abnahme (vor Code) · **Autor:** Engineering
**Basis:** `docs/SPRINT_3_CHARTER.md` (Tracks A–D) + verifizierter Code-Stand
**Entscheidung Jonas (2026-06-01):** Erst Detailplan abnicken, dann Umsetzung. Track D im
**vollen** Umfang (D1 + D2 + D4 + D5).

> Dieses Dokument ist der ausführbare Bauplan. Jede Task nennt **Datei**, **konkrete
> Funktion/Signatur**, **Definition of Done (DoD)** und **Verifikation**. Wo der Charter
> Optionen offen lässt, ist hier eine Entscheidung getroffen und begründet.

---

## 0 — Verifizierter Ausgangszustand (heute)

Vor der Planung gegen den echten Code geprüft:

| Baustein | Status | Fundort (verifiziert) |
|---|---|---|
| Stufe 1 CP-SAT + `generate()` | vorhanden | `src/generator.py:403`, `GeneratorConfig` ab Z. 31 |
| AC-2.1.8 Flags | vorhanden, default **off** | `enforce_ac218_structural` (Z. 78), `enable_lns_ac218_repair` (Z. 84) |
| HAP-Solver | vorhanden, verifiziert worst_away=13 (relaxiert) | `src/colgen/hap.py:29 solve_global_hap` |
| Matchup-Quoten | vorhanden | `src/matchup_extractor.py:76 extract_matchup_quotas` |
| Phase-B Matching | vorhanden (hard + soft) | `src/series_matching.py:272 match_series_slots`, `:494 …_soft` |
| 8-D Bewertung | vorhanden | `src/pareto_types.py:38 ParetoBundle`, `:180 compute_pareto_bundle` |
| Reisemodell | vorhanden | `src/travel.py:89 compute_team_travel` (total_km, total_flight_hours, timezone_hops …) |
| Reale Pläne | vorhanden | `data/mlb_schedule_2024.json`, `data/mlb_schedule_2025.json` |
| AC-Definition (maßgeblich) | vorhanden | `docs/CBA_DEFINITIONS.md` (Formel `days_away = (last-first).days+1`) |
| AC-2.1.8 xfail | vorhanden | `tests/test_fatigue_constraints.py` |

**Sprint-3-Zieldateien sind alle noch leer/absent** — echte Greenfield-Arbeit, kein Umbau:
`tools/q10_compat.py`, `tools/backtest.py`, `src/sustainability.py`, `src/fairness.py`.

**Baseline-Invarianten, die Sprint 3 nicht brechen darf:**
- ~297 Nicht-slow-Tests grün, 2 dokumentierte `xfail`, deterministisch (1 Worker).
- km ~2,07–2,17 Mio über Seeds; Revenue −1,40 % vs. Sportico; AC-2.1.9 strukturell 0.
- Default-Produktionsverhalten unverändert: alle neuen Modi/Constraints **opt-in** hinter Flags.

---

## 1 — Sprint-Goal & Reihenfolge

**Goal:** Die echte CBA-Garantie (AC-2.1.8 ≤ 13) ernsthaft angehen (Track A) **und** das
Produkt so erweitern, dass MLB League Officials ihm vertrauen und es einsetzen würden
(Tracks B–D): nachweisbar besser als der reale Plan (B), nachhaltiger + fairer (C),
verteidigbar + erklärbar (D).

**Reihenfolge** (an serielles Arbeiten angepasst, nicht 3 Teams parallel):

```
Woche 1   │ B1–B3 (Backtest)  →  C1+C2 (CO₂ + Fairness)   │  risikoarm, sofortige Officials-Story
          │ A1–A3 (Spike, ≤1 Woche getimeboxed)            │  Forschung, endet im Entscheidungs-Gate
          ▼
GATE      │ Spike grün → A4 (cba_strict, ≤13-Beweis)
          │ Spike rot  → A4′ (Negativbefund dokumentieren), Kapazität → Track D
          ▼
Woche 2-3 │ A4  ODER  Track D (D1+D2+D4+D5)  +  C3 (Dashboard)  +  B4 (Modell-Validierung)
```

**Begründung der Reihenfolge:** B und C sind schnelle, sichere Wins und liefern unmittelbar
die Glaubwürdigkeits-Story. A ist risikoreich mit frühem Gate — deshalb timeboxen, nicht den
Sprint daran aufhängen. D profitiert von B/C (gemeinsamer Report) und ist der Fallback-Topf
für freiwerdende Kapazität, falls das Gate rot ist.

**Abhängigkeiten:** C3 setzt auf B (gemeinsamer Report-Renderer). D4 (Compliance) profitiert
von A (sauberer AC-2.1.8-Status), ist aber nicht blockiert. Sonst sind die Tracks unabhängig.

---

## 2 — Querschnitts-Konventionen (gelten für jede Task)

1. **Opt-in only.** Kein neues Verhalten ändert den Default. Neue Constraints/Modi hinter
   `GeneratorConfig`-Flags (Muster: `enable_lns_ac218_repair`).
2. **Keine erfundenen Domänendaten.** Emissionsfaktoren, CBA-Wortlaut, TV-Fenster,
   Feiertags-Daten werden **recherchiert + zitiert** (Quelle im Code-Docstring **und** im
   begleitenden Research-Doc). Bis Quelle vorliegt: weiches Incentive + dokumentierte Annahme,
   nie als harte Regel.
3. **Determinismus.** 1 Worker, fixe Seeds, bit-identische Ergebnisse. Jede Zufallsquelle
   nimmt den Seed aus der Config.
4. **Tests + Sauberkeit.** Jede neue Datei: eigene `tests/test_sprint_3_*.py`, `pyflakes`
   sauber, `python -m compileall` ok. Slow-CP-SAT-Tests als `@pytest.mark.slow` (CI-only).
5. **Ehrlichkeit.** Reports benennen, wo wir *nicht* besser sind. Ein rotes A-Gate ist ein
   Befund, kein Makel.

---

## 3 — Track A — AC-2.1.8 strukturell garantieren (Headliner, Forschung)

**Ziel:** deterministischer Modus `generation_mode="cba_strict"`, der einen *vollständigen*
Saisonplan unter den *echten* Matchup-Quoten mit **worst_away ≤ 13 für alle 30 Teams** liefert.
**Ansatz:** matchup-bewusste HAP über eine Logic-Based-Benders-Schleife (HAP → Phase-B-Matching
→ Konflikt-Cut → wiederholen). Die team-übergreifende Kopplung wandert in ein reines
Zuordnungsproblem; das HAP-Modell bleibt per-Team + Cuts tractable.

| # | Task | Datei(en) | DoD | Verifikation |
|---|---|---|---|---|
| **A1** | **Diagnose-Harness.** HAP via `solve_global_hap` lösen, Phase-B (`match_series_slots`) gegen `extract_matchup_quotas` versuchen, die 173/811-Inkompatibilität exakt aufschlüsseln (pro Paarung / Team / Zeitfenster). | `tools/q10_compat.py` (neu) | CLI gibt strukturierte Tabelle aus: welche Paarung hat zu wenige musterkonforme Tag-Slots, wo clustern die Konflikte. | Reproduzierbar auf realer 30-Team-Instanz, fixer Seed; Zahlen gegen bekannte 173/811 plausibilisiert. |
| **A2** | **Benders-Cut-Mechanik.** Aus einer Phase-B-Infeasibility den verletzten Coverage-Constraint ableiten + als HAP-Constraint formulieren (no-good / Coverage-Cut). | `src/colgen/` (neu: `cuts.py` o. Erweiterung `engine.py`) | Funktion nimmt Infeasibility-Zertifikat → liefert gültigen Cut, der dieselbe HAP-Familie ausschließt. Unit-getestet an Mini-Instanz. | Mini-Instanz (4–6 Teams), bei der die Schleife nachweislich konvergiert. |
| **A3** | **Schleife + Konvergenz-Messung** auf realer 30-Team-Instanz (1 Worker, mehrere Seeds, Zeitbudget). **= Entscheidungs-Gate.** | `tools/q10_compat.py` | Messprotokoll: konvergiert / divergiert, Zeit, #Cuts, verbleibende Infeasibility. | Tabelle mit Seeds × Zeit; klares grün/rot-Urteil mit Daten. |
| **A4** *(Gate grün)* | `cfg.generation_mode="cba_strict"` verdrahten; Phase-B mit echten Matchups, Boundary-Single-Games minimieren; **verifizieren worst_away ≤ 13 (alle Teams, alle Seeds)**; xfail entfernen. | `src/generator.py`, `tests/` | Modus erzeugt vollständigen Plan, ≤13 bewiesen, Default unverändert. | Property-Test über mehrere Seeds; AC-2.1.8-xfail in `tests/test_fatigue_constraints.py` → grün. |
| **A4′** *(Gate rot)* | Negativbefund dokumentieren; Branch-and-Price mit kommerziellem Solver (Gurobi/CPLEX) als separates, beschaffungs-gegatetes Item empfehlen; LNS-Repair bleibt Produktivweg. | `docs/Q10_*` | Fundierte, datengestützte Doku der Open-Source-Grenze + Weiterweg. | Review der Messzahlen aus A3. |

**Timebox:** A1–A3 strikt ≤ 1 Woche. **Risiko: HOCH.** Exakte TTP-Verfahren skalieren in der
Literatur zuverlässig bis ~10–16 Teams; 30 sind am Rand. **Mitigation:** Gate + existierender
Fallback (LNS). Ein rotes Gate ist Erkenntnis, kein Scheitern.

**DoD Track A:** Entscheidungs-Gate mit Daten dokumentiert. Grün → verifizierter
`cba_strict`-Modus mit ≤13-Garantie. Rot → ehrlich dokumentierter Negativbefund + klarer Weg.

---

## 4 — Track B — Backtest gegen den echten MLB-Spielplan

**Ziel:** reproduzierbarer Side-by-Side-Report, der unseren Plan dem realen MLB-Plan
gegenüberstellt — der Glaubwürdigkeits-Beweis für Officials.

| # | Task | Datei(en) | DoD | Verifikation |
|---|---|---|---|---|
| **B1** | Realen Plan (`mlb_schedule_2024/2025.json`) laden, mit **unserem** Scoring bewerten (`compute_pareto_bundle`: km, Fatigue, Revenue, TV …) → „MLB-Ist-Baseline". | `tools/backtest.py` (neu) | Funktion liefert vollständiges `ParetoBundle` für den realen Plan. | Bundle-Werte plausibel (Revenue nahe Liga-Total, AC-Zahlen real). |
| **B2** | Unseren Generator unter demselben Saisonfenster/Constraints laufen lassen; Bundle berechnen. | `tools/backtest.py` | Beide Bundles aus identischem Saisonfenster, identischer Quote. | Saisonfenster + Doubleheader-Handling explizit angeglichen. |
| **B3** | Vergleichsbericht (Markdown + HTML) mit Deltas + Pro-Team-Aufschlüsselung. | `tools/backtest.py`, `output/backtest/` | `python -m tools.backtest --season 2024` erzeugt Report mit Delta-Tabelle. | Report manuell gelesen; Deltas vorzeichen-/größenplausibel. |
| **B4** | **Modell-Validierung:** unsere km-Berechnung auf dem realen Plan gegen bekannte Reise-Realität prüfen (eicht das Reisemodell). | `tools/backtest.py` | Abweichung unserer km zu Referenz dokumentiert; Reisemodell ggf. nachgeeicht. | Gegen veröffentlichte Team-Reise-km (Quelle zitiert) abgeglichen. |

**Ehrlichkeits-Gebot:** Unser Plan muss **nicht** auf jeder Achse besser sein (MLB optimiert
auch Ungemodelltes, z. B. nationale TV-Deals). Der Report ist ausgewogen und benennt das.
**Risiko: niedrig–mittel** (Datenausrichtung Saisonfenster / Doubleheader).

**DoD Track B:** `tools/backtest.py` erzeugt reproduzierbaren Side-by-Side-Report mit
dokumentiertem, ehrlichem Delta.

---

## 5 — Track C — CO₂- und Fairness-Reporting

**Ziel:** beide Kennzahlen im Standard-Report **und** Dashboard sichtbar, Methodik belegt.

| # | Task | Datei(en) | DoD | Verifikation |
|---|---|---|---|---|
| **C1** | **CO₂-Modell:** km → Flugemissionen (Charter-Faktor) → CO₂-Tonnen, mit **zitierter** Emissionsfaktor-Quelle; abgeleitete Kennzahl in Report/Bundle. | `src/sustainability.py` (neu) | Funktion `co2_tonnes(travel)` mit dokumentierter Formel + Quelle (kg CO₂ / Flugkm, Charter-Jet). | Größenordnung gegen veröffentlichte Liga-Reise-Emissionen plausibilisiert. |
| **C2** | **Fairness-Metrik:** Verteilung der Pro-Team-km → Gini-Koeffizient + max/min-Verhältnis; als Report-Dimension (optional weiches Ziel). | `src/fairness.py` (neu) | `gini(per_team_km)` + `travel_disparity_ratio()`; Formel dokumentiert. | Gini gegen synthetische Referenzfälle (perfekt gleich → 0) unit-getestet. |
| **C3** | Beide im Vergleichs-Report (Track B) + Dashboard ausweisen. | `dashboard/`, `tools/backtest.py` | CO₂-Tonnen + Fairness-Index erscheinen in Report und Dashboard. | Dashboard manuell geöffnet, Werte erscheinen korrekt. |

**Entscheidung:** Fairness und CO₂ werden als **abgeleitete Report-Kennzahlen** geführt (nicht
sofort als 9./10. Pareto-Dimension), um die bestehende 8-D-`ParetoBundle`-Invariante und alle
Tests stabil zu halten. Aufnahme als weiches Pareto-Ziel ist ein bewusst separates Folge-Item.
**Risiko: niedrig.** Kleiner Aufwand, große Stakeholder-Wirkung.

**DoD Track C:** CO₂-Tonnen + Fairness-Index im Standard-Report; Methodik (Emissionsfaktor,
Gini-Formel) dokumentiert und mit Quelle belegt.

---

## 6 — Track D — Real-Constraints + Erklärbarkeit (voller Umfang: D1+D2+D4+D5)

**Ziel:** realistische fehlende Regeln umsetzen **und** den Plan prüfbar/erklärbar machen.
**Vorarbeit-Gebot:** D2 (Feiertags-Daten) und D4 (CBA-Wortlaut) brauchen echtes
Quellenwissen → recherchieren + zitieren, nicht erfinden.

| # | Task | Datei(en) | DoD | Verifikation |
|---|---|---|---|---|
| **D1** | **Getaway-Day / Reise-Feasibility:** unrealistische Back-to-Backs (z. B. Nachtspiel → Tagspiel über mehrere Zeitzonen) erkennen + als harte Prüfung/Constraint (opt-in) flaggen. | `src/travel.py` o. neu `src/feasibility.py` | Detektor liefert Liste verletzender Spielpaare; opt-in-Constraint im Generator. | Bekannter unrealistischer Fall wird geflaggt; sauberer Plan flaggt nichts. |
| **D2** | **Marquee-/Feiertags-Slots:** Opening Day, 4. Juli, Memorial/Labor Day, Jackie-Robinson-Day als weiche Incentives oder harte Pins (Daten **recherchiert**, vgl. `data/tv_slots.json`). | `src/tv_slots.py`/neu `data/holidays_2026.json` | Datierte Slot-Liste mit Quelle; als Incentive im Scoring. | Daten gegen offiziellen MLB-Kalender geprüft (Quelle zitiert). |
| **D4** | **CBA-Provenance / Audit-Trail:** maschinenlesbares Register, das jede harte Constraint ihrem CBA-Artikel zuordnet; pro Plan ein **Compliance-Report**. | neu `src/compliance.py`, `docs/CBA_DEFINITIONS.md` | `compliance_report(season)` listet je Constraint: CBA-Artikel, Status (erfüllt/verletzt), Messwert. | Report auf einem realen Plan erzeugt; Zuordnung gegen `CBA_DEFINITIONS.md` geprüft. |
| **D5** | **Plan-Begründung:** menschenlesbare Erklärung pro Plan (Reise-Highlights, wo Trade-offs gemacht wurden). | neu `src/explain.py` | `explain_plan(bundle, baseline)` erzeugt prägnanten Fließtext (DE/EN). | Erklärung manuell gelesen; Aussagen stimmen mit Bundle-Zahlen überein. |

**DoD Track D:** D1+D2+D4+D5 umgesetzt; pro Plan wird ein Compliance-/Audit-Report **und** eine
menschenlesbare Begründung erzeugt. **Risiko: mittel** — hängt an Verfügbarkeit echter
Domänendaten; bis dahin dokumentierte weiche Annahmen.

---

## 7 — Sprint-Definition-of-Done (gesamt)

- **Track A:** Entscheidungs-Gate mit Daten dokumentiert; falls grün, verifizierter
  `cba_strict`-Modus mit ≤13-Garantie (xfail entfernt).
- **Track B:** reproduzierbarer Backtest-Report mit ehrlichem Delta.
- **Track C:** CO₂ + Fairness im Standard-Report, Methodik belegt + zitiert.
- **Track D:** D1+D2+D4+D5 umgesetzt; Compliance-Report + Begründung pro Plan.
- **Alle neuen Module:** Tests grün, `pyflakes` sauber, deterministisch, Default-Verhalten
  unverändert.
- `docs/GESAMTBERICHT_FUER_REVIEW.md` und `README.md` auf neuen Stand gebracht.

---

## 8 — Übergreifende Risiken & Mitigation

| Risiko | Mitigation |
|---|---|
| Track A mit Open-Source-Solver unlösbar | Entscheidungs-Gate (A3) + Fallback (LNS existiert) + ehrliche Empfehlung Richtung kommerzieller Solver. Kein Scheitern, sondern Erkenntnis. |
| Fehlende echte MLB-Daten (D2/D4) | Nicht erfinden; recherchieren/zitieren. Bis dahin weiche Annahmen klar dokumentieren. |
| Backtest zeigt: nicht überall besser (B) | Ausgewogen berichten — wissenschaftliche Redlichkeit, kein Makel. |
| Regressionsgefahr durch neue Constraints | Alles opt-in hinter Flags; Baseline-Tests (297 grün) als Gate vor jedem Merge. |
| Determinismus bricht | Seeds aus Config, 1 Worker, `test_invariants` + hypothesis als Wächter. |

---

## 9 — Reihenfolge der Umsetzung (konkrete Schritt-Liste)

1. **B1 → B2 → B3** (`tools/backtest.py`): Backtest-Harness + Report. *(erster sichtbarer Win)*
2. **C1 → C2** (`src/sustainability.py`, `src/fairness.py`): CO₂ + Fairness als Kennzahlen.
3. **A1 → A2 → A3** (`tools/q10_compat.py`, `src/colgen/`): Spike + **Entscheidungs-Gate**.
4. **Gate-Auswertung** → A4 (grün) **oder** A4′ (rot, → Kapazität in D).
5. **C3** (Dashboard) + **B4** (Modell-Validierung).
6. **D1 → D2 → D4 → D5**: Real-Constraints + Compliance + Begründung.
7. **Abschluss:** `GESAMTBERICHT_FUER_REVIEW.md` + `README.md` aktualisieren, volle Test-Suite.

---

*Nächster Schritt nach Abnahme dieses Plans: Start mit Schritt 1 (Track B), erster Win:
reproduzierbarer Backtest-Report „unser Plan vs. realer MLB-Plan".*
