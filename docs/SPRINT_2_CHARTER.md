# Sprint 2 Charter — MLB Logistics Optimizer

**Periode:** 2026-06-05 bis 2026-07-17 (6 Wochen, vier Sub-Sprints à 1,5 Wochen)
**Sprint-Vision:** Aus dem Optimizer-Prototyp eine **Scheduling Decision Engine** machen, die einem MLB-Operations-Team in Stunden liefert, wofür sie heute Wochen brauchen.

---

## Re-Framing — was wir bauen und was nicht

Sprint 1 hat bewiesen, dass wir MLBs Routing-Qualität *nicht* beim Optimum-Punkt schlagen (1% Headroom, 92% schon optimal). Das ist auch nicht das Geschäftsmodell. **Wir verkaufen Geschwindigkeit, Flexibilität und Erklärbarkeit**, nicht 5% bessere km-Zahlen.

Sprint 2 baut deshalb vier Features, die genau diese Werte liefern:

| Sub-Sprint | Feature | Wert | Killer-Frage, die es beantwortet |
|---|---|---|---|
| 2.1 | Schedule-from-Scratch Generator | Geschwindigkeit | "Gib mir in 10 Min einen kompletten Saisonplan, der alle Regeln einhält." |
| 2.2 | Disruption Handler | Resilienz | "Hurricane in Miami nächste Woche — was sind meine Optionen?" |
| 2.3 | Profile Switcher + Pareto Explorer | Tradeoff-Klarheit | "Was kostet uns Player Health an Revenue?" |
| 2.4 | What-if Engine + Audit Trail | Erklärbarkeit | "Warum genau spielt Boston Anfang April in Detroit?" |

---

## Qualitätsmesslatte (zwingend)

Jeder Sub-Sprint hat **Acceptance Criteria** als binäre Pass/Fail-Kriterien. Ein Sub-Sprint gilt erst dann als abgeschlossen, wenn **alle** Kriterien grün sind UND mit automatisierten Tests bewiesen sind.

Test-Strategie:
- `pytest` als Framework
- Coverage-Reporting via `pytest-cov`
- Jeder Sub-Sprint mindestens **80 % Coverage** des betroffenen Code-Pfads
- **Property-based tests** wo sinnvoll (Hypothesis-Library) — z. B. "ein erzeugter Plan hat IMMER 162 Spiele pro Team"
- **Regression-Tests** gegen die Sprint-1-Validierungs-Ergebnisse (wenn wir den Schedule-Loader ändern, dürfen die 2024-Zahlen nicht abweichen)

---

## Sprint 2.1 — Schedule-from-Scratch Generator

**Dauer:** 1,5 Wochen

**Was wir bauen:**
Eine Engine, die aus reinen MLB-Liga-Regeln (kein Vorlage-Plan) einen kompletten 162-Spiele-Plan erzeugt. Methode: **OR-Tools CP-SAT** (Constraint Programming), das ist, was MLB selbst nutzt.

**Acceptance Criteria — alle müssen grün sein:**

| # | Kriterium | Test |
|---|---|---|
| AC-2.1.1 | Erzeugt Plan in **≤ 30 Minuten** auf Standard-Hardware (single-thread) | Timer-Test |
| AC-2.1.2 | Genau **162 Spiele pro Team** (alle 30 Teams) | Unit-Test |
| AC-2.1.3 | Genau **81 Heim + 81 Auswärts** pro Team | Unit-Test |
| AC-2.1.4 | Korrekte **Matchup-Quoten** je Liga-Regel (13 Division, 6+ Liga, 4+ Interleague) | Unit-Test |
| AC-2.1.5 | **All-Star-Break** respektiert (keine Regular-Season-Spiele in den 4 Tagen) | Unit-Test |
| AC-2.1.6 | **Saisonfenster** eingehalten (kein Spiel ausserhalb) | Unit-Test |
| AC-2.1.7 | Keine **doppelten Buchungen** (kein Team an einem Tag in zwei Spielen außer Doubleheader) | Property-Test |
| AC-2.1.8 | **Max. 13 konsekutive Auswärtstage** (CBA-Proxy) | Property-Test |
| AC-2.1.9 | **Min. 1 Off-Day alle 20 Spiele** pro Team | Property-Test |
| AC-2.1.10 | Total km in **Range 1,5–2,0 Mio** (Plausibilität vs. echte MLB-Saison) | Plausibility-Test |
| AC-2.1.11 | **Reproduzierbarkeit** mit Seed | Bit-für-Bit-gleicher Output bei gleichem Seed |
| AC-2.1.12 | **80% Coverage** des `generator.py`-Moduls | pytest-cov |

**Deliverables:**
- `src/generator.py` — CP-SAT-Modell + Solver-Wrapper
- `tests/test_generator.py` — alle Acceptance-Tests
- `output/generated_seasons/season_<id>.json` — Beispiel-Output
- `docs/generator_methodology.md` — Erklärung des CP-SAT-Modells

---

## Sprint 2.2 — Disruption Handler

**Dauer:** 1,5 Wochen

**Was wir bauen:**
Eine Engine, die einen bestehenden Plan plus ein Disruption-Event entgegennimmt und 3–5 valide Alternativ-Pläne mit Tradeoff-Bewertung liefert.

**Disruption-Typen unterstützt:**
- Stadion-Blackout (Datum-Range, Heimteam)
- Wetter-/Naturkatastrophen-Fenster (Stadt + Datums-Range)
- Massen-Postponement (mehrere Spiele auf einmal)

**Acceptance Criteria:**

| # | Kriterium | Test |
|---|---|---|
| AC-2.2.1 | **≤ 60 Sekunden** Response-Zeit für Standard-Disruption (1 Heimserie betroffen) | Timer-Test |
| AC-2.2.2 | Liefert **mindestens 3 valide** Alternativen | Unit-Test |
| AC-2.2.3 | Jede Alternative hält **alle harten Constraints** ein | Validator-Test |
| AC-2.2.4 | Tradeoff-Bewertung pro Alternative (km, Affected Teams, $-Impact) | Output-Schema-Test |
| AC-2.2.5 | **Mindestabweichung-Modus**: eine Alternative ändert ≤ 5 % der Originalspiele | Diff-Test |
| AC-2.2.6 | **Sanity-Test** mit Hurricane-Milton-Szenario (Tropicana Okt 2024) | End-to-End-Test |
| AC-2.2.7 | **Idempotenz**: gleicher Input → gleicher Output | Reproducibility-Test |
| AC-2.2.8 | **80% Coverage** des `disruption.py`-Moduls | pytest-cov |

**Deliverables:**
- `src/disruption.py` — Disruption-Engine
- `src/disruption_types.py` — typisierte Disruption-Schemata
- `tests/test_disruption.py` — alle ACs + Hurricane-Milton-Szenario
- `output/disruption_examples/` — Beispiel-Szenarien mit Outputs
- `docs/disruption_methodology.md`

---

## Sprint 2.3 — Profile Switcher + Pareto Explorer

**Dauer:** 1,5 Wochen

**Was wir bauen:**
Multi-Profile-Pareto-Sampling. Statt einem Plan: N Pläne entlang der Pareto-Front mit interaktiver Tradeoff-Visualisierung.

**Acceptance Criteria:**

| # | Kriterium | Test |
|---|---|---|
| AC-2.3.1 | Generiert **≥ 7 nicht-dominierte** Pläne in einem Lauf | Pareto-Property-Test |
| AC-2.3.2 | Pareto-Frontier-Berechnung in **≤ 5 Minuten** | Timer-Test |
| AC-2.3.3 | Score-Bundle für jeden Plan vollständig (alle 8 Kategorien) | Schema-Test |
| AC-2.3.4 | **Pareto-Dominanz-Validierung**: alle gelieferten Pläne sind nicht-dominiert | Math-Test |
| AC-2.3.5 | **Visualisierung**: 2D-Pareto-Plot (z. B. Travel vs Revenue) | Snapshot-Test |
| AC-2.3.6 | **Anker-Pläne**: erkennt Extrema (min-Travel, max-Revenue, balanced) | Unit-Test |
| AC-2.3.7 | **80% Coverage** des `pareto.py`-Moduls | pytest-cov |

**Deliverables:**
- `src/pareto.py` — Pareto-Sampling-Engine
- `tests/test_pareto.py`
- `output/pareto/` — Beispiel-Frontiers mit Visualisierung
- Updated dashboard panel

---

## Sprint 2.4 — What-if Engine + Audit Trail

**Dauer:** 1,5 Wochen

**Was wir bauen:**
- *What-if-Engine*: simuliert hypothetische Änderungen (Constraint-Ergänzungen, Saison-Fenster-Verschiebung, Matchup-Quoten-Variation) und liefert Diff-Reports.
- *Audit Trail*: pro Spiel/Entscheidung die binding constraints und die Entstehungsgeschichte.

**Acceptance Criteria:**

| # | Kriterium | Test |
|---|---|---|
| AC-2.4.1 | What-if-Run in **≤ 2 Minuten** für eine moderate Änderung | Timer-Test |
| AC-2.4.2 | **Versions-Branching**: jede Was-wäre-wenn-Variante ist eine Branch | Storage-Test |
| AC-2.4.3 | **Diff-Report**: zeigt geänderte Spiele, betroffene Teams, Δ-Kennzahlen | Output-Schema-Test |
| AC-2.4.4 | **Audit-Trail pro Spiel**: liefert binding constraints und Quelle | Per-Game-Test |
| AC-2.4.5 | **Audit-Trail-Roundtrip**: aus Audit-Daten lässt sich der Plan rekonstruieren | Reproducibility-Test |
| AC-2.4.6 | **Storage**: Branches werden in JSON serialisiert (lossless) | Persistence-Test |
| AC-2.4.7 | **80% Coverage** der `whatif.py`- und `audit.py`-Module | pytest-cov |

**Deliverables:**
- `src/whatif.py` — Was-wäre-wenn-Engine
- `src/audit.py` — Audit-Trail-Engine
- `src/versioning.py` — Branch/Storage-Schicht
- `tests/test_whatif.py` + `tests/test_audit.py`
- `output/whatif/` + `output/audit/` — Beispiele
- `docs/audit_format_spec.md` — Daten-Format-Spezifikation

---

## Sprint-Review-Kriterium

Sprint 2 gilt als **erfolgreich abgeschlossen**, wenn:

1. Alle 4 Sub-Sprints "Done" (alle ACs grün, alle Tests passing)
2. **Gesamt-Test-Suite läuft in < 10 Minuten** und ist deterministisch
3. **Coverage-Report** zeigt ≥ 80 % für alle 4 neuen Module
4. **Demo-Skript** (`demo.py`) zeigt alle 4 Features end-to-end in einer Session
5. **Sprint-Review-Dokument** mit harten Zahlen pro Feature

Erst dann Sprint 2 = "Geliefert".
