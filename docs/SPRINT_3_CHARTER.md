# Sprint 3 — Charter & Plan

**Stand:** 2026-05-31 · **Status:** Planung (vor Umsetzung) · **Autor:** Projektteam
**Zweck:** Ein vollständiger, konkreter Plan für Sprint 3 — bewusst so geschrieben, dass auch
jemand, der **noch nie in diesem Projekt gearbeitet hat**, versteht: Was ist das Produkt? Wo
stehen wir? Welche Probleme haben wir gerade wirklich? Und wie machen wir das Produkt richtig
gut — besonders für die echten Nutzer: **MLB League Officials** (die Liga-Verantwortlichen,
die den Spielplan erstellen, verteidigen und gegen den Tarifvertrag prüfen).

> Wenn du neu bist: lies **Teil 0** (Orientierung) und das **Glossar** am Ende zuerst. Danach
> ergeben Teil 1–4 vollen Sinn.

---

## Teil 0 — Orientierung für Neue (Was ist dieses Projekt?)

**Das Problem in einem Satz.** Die MLB-Saison hat 30 Teams, die je 162 Spiele bestreiten —
zusammen 2.430 Spiele über ~186 Tage. Diese Spiele auf Tage und Stadien zu verteilen ist ein
riesiges Optimierungsproblem: Man will **wenig Reisedistanz** (Kosten, Spielergesundheit,
CO₂), **hohe Einnahmen** (Gate + TV), und muss zugleich **harte Regeln** einhalten — sowohl
sportliche (jeder spielt jeden, Heim/Auswärts-Balance) als auch Tarifvertrags-Regeln (CBA)
zum Schutz der Spieler.

**Was unser System tut.** Es baut automatisch einen optimierten Alternativplan und bewertet
ihn über **acht Zieldimensionen**. Es liefert nicht *eine* Lösung, sondern eine **Pareto-Front**
mehrerer sinnvoller Alternativen (damit Officials Trade-offs bewusst wählen), plus eine
**What-if-Engine** für schnelle Szenario-Fragen.

**Die Pipeline in einfachen Worten:**

1. **Stufe 1 — CP-SAT (ein Constraint-Solver von Google OR-Tools).** Platziert alle
   Spielserien so, dass kein Team zwei Spiele am selben Tag hat und die Off-Day-Regel
   (AC-2.1.9) strukturell eingehalten ist. Ergebnis: ein gültiger Plan in ~0,2 Sekunden.
2. **Stufe 2 — Simulated Annealing (ein Optimierungs-Verfahren).** Verschiebt Serien, um die
   **Reisedistanz** zu minimieren, ohne Regeln zu verletzen.
3. **Pareto-Explorer.** Läuft Stufe 2 mit verschiedenen Gewichtungen → eine Menge
   nicht-dominierter Pläne.
4. **What-if & Disruption.** Schnelle lokale Re-Planung („Was, wenn Stadion X gesperrt ist?").

**Wichtige Dateien (Einstieg):**

| Datei | Rolle |
|---|---|
| `src/generator.py` | Stufe 1 (CP-SAT) + Haupt-Einstieg `generate()` |
| `src/generator_optimizer.py` | Stufe 2 (Simulated Annealing) + Fatigue-Repair |
| `src/pareto.py`, `src/pareto_types.py` | Pareto-Front + die 8 Bewertungs-Dimensionen |
| `src/player_fatigue.py` | CBA-Regeln AC-2.1.8/9 (Mess- & Prüf-Funktionen) |
| `src/whatif_core/` | What-if-Engine (Subpackage) |
| `src/colgen/` | Akademische HAP/Column-Generation-Pipeline (Backup) |
| `docs/CBA_DEFINITIONS.md` | Verbindliche Definition der CBA-Regeln |
| `docs/Q10_ANALYSE_UND_RECHERCHE.md` | Tiefe Analyse des Hauptproblems (siehe Teil 2) |
| `docs/GESAMTBERICHT_FUER_REVIEW.md` | Vollständiger Statusbericht |

**So führt man es aus:**
```bash
pip install -r requirements.txt
python -m src.main --season 2026 --pareto      # Plan + Pareto-Front
uvicorn tools.api:app --reload                 # REST-API (optional)
```

---

## Teil 1 — Wo wir heute stehen (verifiziert)

- Voller Saisonplan **deterministisch in ~15–35 s**. Reisedistanz konvergiert über alle
  getesteten Seeds auf **~2,07–2,17 Mio km**.
- **AC-2.1.9** (max. 20 Spieltage je 21-Tage-Fenster): **strukturell garantiert, 0 Verletzungen.**
- **Revenue-/TV-Modell** auf **−1,40 %** zur Sportico-Liga-Summe geeicht.
- **Pareto-Front, What-if-Engine, Disruption-Handler** funktionsfähig.
- **REST-API-Skelett** (FastAPI), interaktives **D3-Dashboard**.
- Code sauber & modular (Subpackages `colgen/`, `whatif_core/`), **~297 Tests grün**,
  2 dokumentierte `xfail`, deterministisch reproduzierbar.

Mit anderen Worten: Der Kern steht und ist solide. Was fehlt, sind (a) **eine echte
Garantie für die zweite CBA-Regel** und (b) eine Reihe von Dingen, die das Produkt von
„technisch beeindruckend" zu „wird von der Liga tatsächlich eingesetzt" heben.

---

## Teil 2 — Welche Probleme wir *gerade wirklich* haben

### Problem 1 (das große) — AC-2.1.8 ist nicht strukturell garantiert

**Was die Regel sagt.** AC-2.1.8 (Tarifvertrag) begrenzt, wie lange ein Team am Stück „weg
von zu Hause" sein darf: **maximal 13 Tage**. Wichtig — **Off-Days mitten in einer Reise
zählen mit** (das Team ist ja weiter unterwegs). Eine Reise von „Auswärts, Off, Auswärts …"
über 14 Kalendertage ist also eine Verletzung, selbst wenn nicht an jedem Tag gespielt wird.

**Was unser System heute tut.** Es setzt AC-2.1.8 nur **weich** durch: Die Simulated-Annealing-
Stufe bestraft Verletzungen stark und ein Repair-Schritt bricht zu lange Reisen auf. Ergebnis:
deutlich reduziert, aber **nicht garantiert ≤13** — je nach Seed bleiben **2–6 Teams** mit
Worst-Case **17–24 Tagen** übrig. Im Test ist das ein ehrlicher `xfail`.

**Warum ist das so schwer? (Kern verständlich erklärt.)** Jede Spielserie ist **gleichzeitig
ein Heimspiel für das eine und ein Auswärtsspiel für das andere Team**. Wenn man also die
Reise-Obergrenze für alle 30 Teams gleichzeitig hart erzwingen will, hängen alle 30 Teams
über genau dieselben Variablen zusammen. Der Suchraum explodiert. Das ist kein Bug, sondern
eine bekannte mathematische Härte: Es ist das **Traveling Tournament Problem (TTP)**, das
**APX-hart** ist (es gibt nachweislich keine einfache, schnell lösbare Formulierung).

**Was wir bereits bewiesen haben.** Wir haben **sieben** CP-SAT-Standardansätze durchprobiert
(monolithische Gap-Formulierung, mit Break-Anker, Drei-Phasen-Decomposition, Fix-and-Optimize,
FIXED_SEARCH, Automaton/Regular-Constraint, Automaton + lokale Domain) — **alle intraktabel**
(Solver liefert „UNKNOWN", findet also weder Lösung noch Beweis der Unlösbarkeit in
vernünftiger Zeit). Details mit Messzahlen: `docs/Q10_ANALYSE_UND_RECHERCHE.md`.

**Was wir *schon* gebaut haben, das hilft.**
- `colgen.solve_global_hap` erzeugt **Home-Away-Muster pro Team**, die AC-2.1.8 **by
  construction** einhalten (verifiziert: worst_away = 13). **Aber** in einer *relaxierten*
  Variante: Die Muster wissen nichts von den konkreten Paarungen — gekoppelt mit den echten
  Matchup-Quoten sind **173 von 811 Serien** nicht platzierbar.
- Ein optionaler **gefensterter LNS-Repair** (`enable_lns_ac218_repair`, default aus) senkt
  die Verletzer messbar (≈4–9 → 3), liefert aber **keinen** ≤13-Beweis.

**Fazit:** Eine echte Garantie braucht **fortgeschrittene OR-Methodik** — matchup-bewusste
HAP-Generierung oder Branch-and-Price. Genau das ist der Headliner von Sprint 3 (Track A).

### Problem 2 — Dem Produkt fehlt der Beweis „besser als der echte Plan"

Wir behaupten Einsparungen, haben sie aber **nie gegen den realen MLB-Spielplan
quantifiziert**. Für Officials ist das *der* Glaubwürdigkeits-Test — und er validiert
zugleich unser Modell. (→ Track B)

### Problem 3 — Officials-relevante Kennzahlen fehlen

**CO₂** (MLB hat öffentliche Klimaziele) und **Reise-Fairness** (km-Minimierung kann einzelne
Teams systematisch benachteiligen → Wettbewerbsintegrität) werden aktuell nicht ausgewiesen.
(→ Track C)

### Problem 4 — Mehrere echte MLB-Regeln fehlen, und der Plan ist nicht „verteidigbar"

Es fehlen u. a. **Getaway-Days / realistische Reise-Feasibility**, **Marquee-/Feiertags-Slots**,
**National-TV-Fenster** als harte Anforderung, **Venue-Konflikte**. Und Officials brauchen
**Erklärbarkeit**: jede harte Regel nachvollziehbar dem CBA-Artikel zugeordnet, plus
menschenlesbare Begründungen, um den Plan zu prüfen und zu verteidigen. (→ Track D)

---

## Teil 3 — Sprint-3-Plan (vier Tracks)

> Sprint-Goal: **Die echte CBA-Garantie ernsthaft angehen (Track A) und das Produkt so
> erweitern, dass MLB League Officials ihm vertrauen und es einsetzen würden (Tracks B–D).**

### Track A — AC-2.1.8 strukturell garantieren (Headliner, Forschungs-Track)

**Problem:** siehe Teil 2.1. **Ziel:** ein deterministischer Generierungs-Modus, der einen
*vollständigen* Saisonplan unter den *echten* Matchup-Quoten mit **worst_away ≤ 13 für alle
30 Teams** liefert.

**Ansatz — matchup-bewusste HAP über eine Logic-Based-Benders-Schleife.** Wir haben die
Bausteine (HAP-Solver, Phase-B-Matching). Die fehlende Brücke ist die Matchup-Kompatibilität.
Idee der Schleife:
1. HAP generieren (AC-2.1.8/9 by construction).
2. Phase-B: die *echten* Serien aus `extract_matchup_quotas` den musterkonformen Tagen
   zuordnen (CP-SAT/Flow-Problem).
3. Bei Infeasibility einen **Konflikt-Cut** extrahieren (welche Paarung hat zu wenige
   kompatible Tag-Slots?) und ins HAP-Modell zurückspielen.
4. Wiederholen, bis ein vollständiger, ≤13-konformer Plan steht.

Der Clou: Das HAP-Modell bleibt tractable (per-Team-Muster + Cuts), die team-übergreifende
Kopplung wandert in ein reines Zuordnungsproblem.

**Tasks:**

| # | Task | Datei(en) | Aufwand |
|---|---|---|---|
| A1 | **Diagnose-Harness:** HAP lösen, Phase-B gegen echte Quoten versuchen, die 173/811-Inkompatibilität exakt aufschlüsseln (pro Paarung/Team/Zeitfenster) | `tools/q10_compat.py` (neu) | 1–2 d |
| A2 | **Benders-Cut-Mechanik:** aus einer Phase-B-Infeasibility den verletzten Coverage-Constraint ableiten + als HAP-Constraint formulieren | `src/colgen/` | 2–3 d |
| A3 | **Schleife + Konvergenz-Messung** auf der realen 30-Team-Instanz (1-Worker, mehrere Seeds, Zeitbudget). **Entscheidungs-Gate.** | `tools/q10_compat.py` | 2–3 d |
| A4 (falls A3 grün) | `cfg.generation_mode="cba_strict"` verdrahten; Phase-B mit echten Matchups, Boundary-Single-Games minimieren; **verifizieren worst_away ≤ 13 (alle Teams, alle Seeds)**; Test + xfail für diesen Modus entfernen | `src/generator.py`, `tests/` | 1–2 Wo |
| A4′ (falls A3 rot) | Negativ-Ergebnis dokumentieren; Branch-and-Price mit kommerziellem Solver (Gurobi/CPLEX) als separates, beschaffungs-gegateteres Item empfehlen; LNS-Repair bleibt Produktivweg | `docs/` | 0,5 d |

**Definition of Done:** Das Entscheidungs-Gate (A3) ist mit Daten dokumentiert. Falls grün:
ein verifizierter `cba_strict`-Modus mit ≤13-Garantie. Falls rot: ein ehrlich dokumentierter,
fundierter Negativbefund + klarer Weiterweg.

**Risiko: HOCH (Forschung).** Exakte TTP-Verfahren skalieren in der Literatur zuverlässig bis
~10–16 Teams; volle 30 sind am Rand. **Mitigation:** strikt timeboxen (A1–A3 ≤ 1 Woche),
Entscheidungs-Gate, Fallback (LNS) existiert bereits. **Wichtig: ein rotes Gate ist kein
Scheitern**, sondern eine fundierte Erkenntnis über die Grenze von Open-Source-Solvern.

### Track B — Backtest gegen den echten MLB-Spielplan

**Problem:** kein quantifizierter Vergleich. **Ziel:** ein reproduzierbarer Bericht, der
unseren Plan dem realen Plan gegenüberstellt — der Glaubwürdigkeits-Beweis für Officials.

**Tasks:**

| # | Task | Datei(en) | Aufwand |
|---|---|---|---|
| B1 | Realen Plan (`mlb_schedule_2024/2025.json`) laden und mit **unserem** Scoring bewerten (km, Fatigue, Revenue, …) → „MLB-Ist-Baseline" | `tools/backtest.py` (neu) | 1 d |
| B2 | Unseren Generator unter demselben Saisonfenster/Constraints laufen lassen; Bundle berechnen | `tools/backtest.py` | 0,5 d |
| B3 | Vergleichsbericht (Markdown/HTML) mit Deltas + Pro-Team-Aufschlüsselung | `tools/backtest.py`, `output/` | 1–2 d |
| B4 | **Validierung:** unsere km-Berechnung auf dem realen Plan gegen bekannte Reise-Realität prüfen (eicht das Reisemodell) | `tools/backtest.py` | 0,5–1 d |

**Definition of Done:** `tools/backtest.py` erzeugt einen Side-by-Side-Report mit
dokumentiertem Delta. **Ehrlichkeits-Gebot:** unser Plan muss nicht auf *jeder* Achse besser
sein (MLB optimiert auch Dinge, die wir nicht modellieren, z. B. nationale TV-Deals) — der
Bericht ist ausgewogen und benennt das.

**Risiko: niedrig–mittel** (Datenausrichtung Saisonfenster/Doubleheader).

### Track C — CO₂- und Fairness-Reporting

**Problem:** ESG- und Wettbewerbsintegritäts-Kennzahlen fehlen. **Ziel:** beide im
Standard-Report (und Dashboard) sichtbar.

**Tasks:**

| # | Task | Datei(en) | Aufwand |
|---|---|---|---|
| C1 | **CO₂-Modell:** km → Flugemissionen (Charter-Faktor) → CO₂-Tonnen, mit zitierter Emissionsfaktor-Quelle; als abgeleitete Kennzahl in Report/Bundle | `src/travel.py` o. `src/sustainability.py` (neu) | 1–2 d |
| C2 | **Fairness-Metrik:** Verteilung der Pro-Team-km → Gini-Koeffizient bzw. max/min-Verhältnis; als Report-Dimension (optional als weiches Ziel) | `src/pareto_types.py`, `src/fairness.py` (neu) | 1–2 d |
| C3 | Beide im Vergleichs-Report (Track B) + Dashboard ausweisen | `dashboard/`, `tools/` | 1 d |

**Definition of Done:** CO₂-Tonnen und ein Fairness-Index erscheinen im Standard-Report; die
Methodik (Emissionsfaktor, Gini-Formel) ist dokumentiert und mit Quelle belegt.

**Risiko: niedrig.** Kleiner Aufwand, große Stakeholder-Wirkung.

### Track D — Real-Constraints + Erklärbarkeit

**Problem:** mehrere echte Regeln fehlen; der Plan ist nicht „verteidigbar". **Ziel:** einen
realistischen Teil der fehlenden Regeln umsetzen **und** den Plan prüfbar/erklärbar machen.

> **Vorarbeit (wichtig!):** Einige Punkte brauchen **echtes MLB-Quellenwissen** (exakter
> CBA-Wortlaut, reale TV-Fenster-Anforderungen, Venue-Konflikt-Kalender). Diese Daten **nicht
> erfinden** — recherchieren bzw. mit MLB-Ops abklären, bevor sie als harte Regel codiert
> werden. Bis dahin als weiche Incentives oder dokumentierte Annahmen führen.

**Tasks (Auswahl für Sprint 3 — realistisch ~1 Woche, nicht alles):**

| # | Task | Aufwand |
|---|---|---|
| D1 | **Getaway-Day / Reise-Feasibility:** unrealistische Back-to-Backs erkennen (z. B. Nachtspiel → Tagspiel über mehrere Zeitzonen) und als harte Prüfung/Constraint flaggen | 2–3 d |
| D2 | **Marquee-/Feiertags-Slots:** Opening Day, 4. Juli, Memorial/Labor Day, Jackie-Robinson-Day als weiche Incentives oder harte Pins | 1–2 d |
| D3 | **National-TV-Fenster:** sicherstellen, dass die Broadcast-Slots tatsächlich gefüllt werden (auf `tv_slots.py` aufsetzen) | 1–2 d |
| D4 | **CBA-Provenance / Audit-Trail:** maschinenlesbares Register, das jede harte Constraint ihrem CBA-Artikel zuordnet; pro Plan ein **Compliance-Report** | 2–3 d |
| D5 | **Plan-Begründung:** menschenlesbare Erklärung pro Plan (Reise-Highlights, wo Trade-offs gemacht wurden) | 1–2 d |

**Definition of Done:** Ein definierter Teilumfang (Empfehlung: D1 + D4 als Kern, D2/D3/D5
nach Kapazität) ist umgesetzt; pro Plan wird ein Compliance-/Audit-Report erzeugt.

**Risiko: mittel** — hängt an der Verfügbarkeit echter Domänendaten.

---

## Teil 4 — Reihenfolge, Abhängigkeiten, Definition of Done

**Empfohlene Sequenz:**

1. **Woche 1:** Track A Spike (A1–A3) **parallel** zu Track B (B1–B3) und Track C (C1–C2).
   Begründung: A ist risikoreich mit frühem Entscheidungs-Gate; B und C sind schnelle Wins,
   die sofort die Officials-Story liefern (besser als real + nachhaltiger + fairer).
2. **Entscheidungs-Gate (Ende Woche 1):** Track-A-Spike grün? → A4 (Voll-Modus). Rot? → A4′
   (dokumentieren) und Kapazität in Track D umlenken.
3. **Woche 2–3:** A4 *oder* Track D (Real-Constraints + Erklärbarkeit), plus C3 (Reporting im
   Dashboard) und B4 (Modell-Validierung).

**Abhängigkeiten:** C3 setzt auf B (gemeinsamer Report). D4 (Compliance-Report) profitiert
von A (sauberer AC-2.1.8-Status). Sonst sind die Tracks weitgehend unabhängig.

**Sprint-Definition-of-Done (gesamt):**
- Track A: Entscheidungs-Gate mit Daten dokumentiert; falls grün, verifizierter `cba_strict`-Modus.
- Track B: reproduzierbarer Backtest-Report mit ehrlichem Delta.
- Track C: CO₂ + Fairness im Standard-Report, Methodik belegt.
- Track D: Kern-Teilumfang umgesetzt + Compliance-Report pro Plan.
- Alle neuen Module: Tests grün, `pyflakes` sauber, deterministisch.
- `docs/GESAMTBERICHT_FUER_REVIEW.md` und README auf den neuen Stand gebracht.

**Übergreifende Risiken & Mitigation:**
- *Track A unlösbar mit Open-Source-Solvern* → Entscheidungs-Gate + Fallback (LNS) + ehrliche
  Empfehlung Richtung kommerzieller Solver. Kein Scheitern, sondern Erkenntnis.
- *Fehlende echte MLB-Daten (Track D)* → nicht erfinden; recherchieren/abklären, bis dahin
  weiche Annahmen klar dokumentieren.
- *Backtest zeigt, dass wir nicht überall besser sind (Track B)* → ausgewogen berichten; das
  ist wissenschaftliche Redlichkeit, kein Makel.

---

## Glossar (für Neue)

- **CBA** — Collective Bargaining Agreement, der Tarifvertrag zwischen MLB und der
  Spielergewerkschaft. Enthält Spielerschutz-Regeln, u. a. zu Reise/Ruhe.
- **AC-2.1.8** — CBA-Regel: max. 13 „days away from home" am Stück (Off-Days zählen mit).
- **AC-2.1.9** — CBA-Regel: max. 20 Spieltage in jedem 21-Tage-Fenster (mind. 1 Off-Day/21 Tage).
- **CP-SAT** — Constraint-Solver von Google OR-Tools (findet regelkonforme Pläne).
- **Simulated Annealing (SA)** — Optimierungs-Verfahren, das durch zufällige, zunehmend
  konservative Verschiebungen ein gutes (km-armes) Ergebnis sucht.
- **Pareto-Front** — die Menge der Pläne, bei denen man keine Dimension verbessern kann, ohne
  eine andere zu verschlechtern. Macht Trade-offs explizit.
- **HAP** — Home-Away-Pattern: für jedes Team eine Tagesfolge aus Heim (H) / Auswärts (A) /
  Off (O).
- **TTP** — Traveling Tournament Problem: das mathematische Modell hinter Sport-Scheduling mit
  Reise-Obergrenzen; **APX-hart** (keine einfache exakte Schnelllösung).
- **Branch-and-Price** — exaktes OR-Verfahren (Spaltengenerierung + Branching), Standardweg für
  schwere TTP-Instanzen.
- **Logic-Based Benders / „first-break-then-schedule"** — Dekomposition: erst Muster (Break),
  dann Spiele zuordnen (schedule); bei Konflikten Cuts zurückspielen.
- **Boundary Single Games** — durch die HAP-Dekomposition entstehende Einzelspiele (Serienlänge
  1) an Block-Rändern; meist unvermeidbarer, kleiner Qualitätsverlust.

---

## Anhang — Referenzen

- `docs/Q10_ANALYSE_UND_RECHERCHE.md` — vollständige AC-2.1.8-Analyse + Literatur-Recherche
- `docs/CBA_DEFINITIONS.md` — verbindliche AC-Definitionen
- `docs/GESAMTBERICHT_FUER_REVIEW.md` — aktueller Gesamtstatus
- `docs/REFACTOR_BACKLOG.md` — erledigte (Q10, A20/A21) + offene Architektur-Items
- `docs/ARCHITECTURE_DECISION.md` — Haupt- vs. Backup-Pipeline
