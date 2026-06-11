# Q10 — AC-2.1.8 strukturell durchsetzen: Analyse, Recherche & Lösung

**Datum:** 2026-05-31
**Status:** Problem analysiert, Stand der Technik recherchiert, **elegante Lösung identifiziert und im eigenen Code verifiziert**.
**Kurzfassung:** Der monolithische Ansatz (AC-2.1.8 als globaler Constraint im
Produktions-Generator) ist nachweislich nicht tragfähig — das ist kein Implementierungs-,
sondern ein Modellproblem. Die Fachliteratur (Traveling Tournament Problem) und unser
eigener `column_generation.py` zeigen übereinstimmend denselben eleganten Weg:
**Dekomposition über Home-Away-Patterns pro Team.** Dieser Weg ist im Projekt bereits
gebaut und liefert verifiziert `worst_away = 13`.

---

## 1. Das Problem

AC-2.1.8 verlangt: Kein Team ist länger als **13 „days away from home"** unterwegs. Nach
der CBA-Definition (`docs/CBA_DEFINITIONS.md`) ist eine Road-Trip die Spanne vom ersten
bis zum letzten Auswärtsspiel; **Off-Days mittendrin zählen mit**, nur ein Heimspiel
beendet sie.

Der Produktionspfad (`generator.py`) setzt AC-2.1.8 aktuell nur **weich** durch:
CP-SAT platziert Serien (mit periodischen Break-Days für AC-2.1.9), danach drückt eine
Simulated-Annealing-Stufe mit hoher Penalty (λ = 1.000.000) plus Greedy-Repair die
Verletzungen herunter. Gemessen am realen 2026-Plan (Seed 42) bleiben damit typischerweise
~4 Teams über dem Limit (worst-case ~20 Tage). Das xfail
`test_AC_2_1_8_realer_generator_haelt_konsekutive_away_limit` dokumentiert das ehrlich.

Ziel von Q10: AC-2.1.8 **strukturell garantieren** (worst_away ≤ 13, zuverlässig, auch
1-Worker-deterministisch), dann das xfail entfernen.

---

## 2. Warum es schwer ist

Das hier ist eine Instanz des **Traveling Tournament Problem (TTP)** — eines der am
besten untersuchten Probleme der Sport-Scheduling-Forschung. Die Constraint „höchstens k
konsekutive Auswärtsspiele/-tage" ist die definierende Schwierigkeit des TTP. Das Problem
ist **APX-hart** (Thielen/Westphal; arXiv:2308.14124) — es gibt keinen Grund, eine
einfache, schnell lösbare globale Formulierung zu erwarten.

Der konkrete Härtegrund in unserem Modell: Jede Serie ist **gleichzeitig Heim für ein und
Auswärts für das andere Team**. Die Road-Trip-Limits aller 30 Teams greifen damit auf
**dieselben** Entscheidungsvariablen zu. Eine globale CP-SAT-Formulierung koppelt also alle
30 Teams über die Serien-Platzierung — und genau diese Kopplung macht den Suchraum
unlösbar groß.

---

## 3. Was wir versucht haben (7 Ansätze, alle UNKNOWN)

Alle Formulierungen sind **korrekt/sound** (gegen ein Brute-Force-Orakel verifiziert); sie
scheitern **ausschließlich** an der Solver-Tractability. Gemessen an der realen Instanz
(811 Serien, Seed 42, 1-Worker, sofern nicht anders vermerkt):

| # | Ansatz | Größe | Ergebnis |
|---|---|---|---|
| 1 | Monolithische Gap-/Nachfolger-Formulierung | ~23k Bools | UNKNOWN / 35 s |
| 2 | Gap + virtueller Break-Heimstand (Anker) | ~23k Bools | UNKNOWN / 35 s |
| 3 | Drei-Phasen-Decomposition um den All-Star-Break | je ~halb | UNKNOWN (Phase 1, auch 4-Worker/35 s) |
| 4 | Globales Fix-and-Optimize ±K um gap-freies Skelett | — | K=6 INFEASIBLE, K=10 UNKNOWN |
| 5 | FIXED_SEARCH (Skelett-Starts zuerst) | ~23k | UNKNOWN / 36 s |
| 6 | `AddAutomaton` über Heim-Tagesindikator | ~150k Bools | UNKNOWN / 22 s |
| 7 | `AddAutomaton` + ±14-Domain + Warm-Start | ~23k Bools | UNKNOWN / 25 s |

**Die entscheidende Erkenntnis** liefert der Vergleich von #1 und #7: Selbst wenn man die
stärkste Propagation (Automaton) mit der schlanksten Größe (23k Bools) kombiniert, löst es
nicht. Die Härte liegt also **nicht** an der Encoding-Größe oder der Propagationsstärke,
sondern ist **intrinsisch in der Kombinatorik** des global gekoppelten Modells.

---

## 4. Was die Fachliteratur sagt

Die Recherche (Easton/Nemhauser/Trick; Irnich; u. a.) ist eindeutig: Niemand setzt die
Road-Trip-Länge als globalen Constraint auf der Spielplatzierung durch. Stattdessen zwei
etablierte Dekompositions-Familien:

**a) Branch-and-Price (exakt).** Ein **Pricing-Subproblem pro Team** generiert nur Touren
(Road-Trips), die das Längenlimit **per Konstruktion** einhalten (ein
ressourcenbeschränktes Kürzeste-Wege-Problem). Die Limit-Constraint ist damit nie global,
sondern in der Spaltengenerierung gekapselt. (Easton/Nemhauser/Trick 2003; Irnich 2009,
„A new branch-and-price algorithm for the TTP".)

**b) „First-break-then-schedule" / Home-Away-Pattern (HAP).** Phase 1: Jedes Team bekommt
ein **Home-Away-Pattern** (pro Tag H/A/Off), das das Konsekutiv-Limit **pro Team einzeln**
erfüllt — das ist billig, weil pro Team entkoppelt. Phase 2: Spiele werden den Tagen so
zugeordnet, dass sie zu den Patterns passen (an jedem Tag #Heim = #Auswärts). Die harte
Limit-Constraint wird komplett in Phase 1 erledigt, wo sie pro Team **trivial** lösbar ist.

Beide Familien sagen dasselbe: **Die Konsekutiv-Constraint gehört in eine team-separierte
Vorstufe, nicht in das global gekoppelte Platzierungsmodell.** Genau das fehlt dem
`generator.py`-Pfad — und genau das erklärt, warum unsere 7 Ansätze scheitern mussten.

---

## 5. Der Durchbruch: Die elegante Lösung ist bereits gebaut

Das Projekt enthält die HAP-Dekomposition bereits — aus Sprint 2.3a, in
`src/column_generation.py` (`solve_global_hap`) und `src/two_phase_pacing.py`. Dort wird
AC-2.1.8 über die **starke, sound Form** `sum(home[d : d+14]) >= 1` (mind. ein Heimtag in
jedem 14-Tage-Fenster ⇔ keine 14 konsekutiven Nicht-Heim-Tage ⇔ Spanne ≤ 13)
durchgesetzt — **pro Team, im Tag×Team-Pattern-Modell**, nicht gekoppelt mit der
Serien-Intervall-Platzierung.

**Eigene Verifikation (2026-05-31), reale Instanz, 30 Teams, Seed 42:**

```
solve_global_hap(...) → status = OPTIMAL  (~16 s in der Sandbox, ~11 s laut Sprint-2.3a-CI)
worst CBA "days away from home" über ALLE 30 Teams = 13
Teams über dem Limit: keine
```

Das ist exakt der Constraint (#6/#7), der im `generator.py`-Modell UNKNOWN liefert — im
HAP-Modell löst er **OPTIMAL**. Der Unterschied ist allein das **Modell**: Das HAP-Modell
arbeitet auf per-Team-Tagesvariablen, wo AC-2.1.8 eine lokale per-Team-Eigenschaft ist; das
Serien-Intervall-Modell von `generator.py` koppelt alle Teams über die geteilte
Platzierung.

**Damit ist die strukturelle AC-2.1.8-Durchsetzung im HAP-Modell gelöst — aber in einer
*relaxierten* Variante (siehe §5a).**

### 5a. Wichtige Einschränkung (verifiziert 2026-05-31): die HAP-Muster sind nicht matchup-kompatibel

`solve_global_hap` erzeugt AC-2.1.8-konforme H/A/Off-Muster mit per-Tag-Paarbalance
(#Heim = #Auswärts), **kennt aber die konkreten Matchups nicht**. Es löst also die
*relaxierte* Frage „existiert ein konformes Heim/Auswärts-Muster?", nicht „… eines, das die
2024er-Matchup-Quoten realisiert?".

Direkter Test (Option A naiv): die 811 echten `extract_matchup_quotas`-Serien auf die
musterkonformen Tage platzieren (Heim-Team `H`, Auswärts-Team `A` über die ganze Serie) mit
per-Team-NoOverlap. Ergebnis:

```
Serien mit LEERER musterkonformer Domain: 173 / 811
Platzierungs-Status: INFEASIBLE (sofort)
```

Für 173 Matchups gibt es **keinen** Tag, an dem das Heim-Team `H` und das Auswärts-Team `A`
ist (z. B. NYY müsste BOS hosten, aber an allen NYY-Heimtagen ist BOS ebenfalls zu Hause).
Das ist exakt die in Sprint 2.3a/QA-Audit dokumentierte **Phase-B-Inkompatibilität**: Der
HAP-Pfad ist eine **parallele Welt mit emergenten Matchups**, nicht der quotengetriebene
Produktionsplan.

**Konsequenz:** Die elegante Dekomposition löst AC-2.1.8, aber „einfach die fertigen
HAP-Muster nehmen" funktioniert nicht. Damit es funktioniert, müssten die Muster
**matchup-bewusst** erzeugt werden (HAP-Generierung + Matchup-Realisierbarkeit gemeinsam) —
und das ist im Kern wieder das volle, APX-harte TTP. Die Kopplung verschwindet nicht, sie
verschiebt sich nur von der Platzierung in die Mustererzeugung.

---

## 6. Warum es ein offenes Item bleibt

Die HAP/Column-Generation-Pipeline ist aktuell **test-only** (`tests/test_sprint_2_3a.py`),
nicht der Produktionspfad. Der Produktionspfad ist `generator.py` (Serien-CP-SAT + SA).
Zwei bekannte Punkte stehen einer 1:1-Übernahme im Weg:

1. **Phase B (`series_matching.py`) ist soft:** Beim Zuordnen der Spiele zu den HAP-Tagen
   entstehen ~89 „Boundary Single Games" (≈ 3,7 % der Serien werden Länge 1). Das ist eine
   strukturelle Eigenschaft der HAP-Dekomposition, in Sprint 2.3a als „OPTIMAL/strukturell
   minimal" dokumentiert. Für die Produktion müsste man entweder diese Single-Games
   akzeptieren (sie sind valide Spiele, nur ungünstig gruppiert) oder Phase B verschärfen.
2. **Architektur-Entscheidung:** Welcher Pfad ist der Hauptpfad? Das ist genau die in
   `docs/ARCHITECTURE_DECISION.md` / Sprint 2.8 angerissene Frage. Q10 sauber zu schließen
   heißt, sie zu beantworten.

---

## 7. Optionen, Q10 zu schließen (mit Trade-offs)

**Option A — HAP-Pattern als Constraint-Quelle für `generator.py` (naiv: VERWORFEN, §5a).**
Idee: `solve_global_hap`-Muster nehmen und die Serien-Platzierung daran koppeln. Getestet
und **infeasible** — die generischen Muster sind nicht matchup-kompatibel (173/811 Serien
ohne konformen Tag). Funktioniert nur mit **matchup-bewusster** HAP-Generierung, die
Matchup-Realisierbarkeit in `solve_global_hap` integriert — das ist im Kern wieder das volle
APX-harte TTP (hoher, forschungsnaher Aufwand, unsicher).

**Option B — HAP/Column-Generation-Pipeline zum Produktionspfad machen.**
Die vollständige Sprint-2.3a-Pipeline (HAP + series_matching + Travel-Optimierung)
übernehmen. Vorteil: AC-2.1.8 by construction, literatur-konform. Nachteil: die 89 Boundary
Single Games + Architektur-Umbau (Sprint 2.8). Aufwand: hoch.

**Option C — Branch-and-Price ausbauen.**
Das `column_generation.py`-RMP/Pricing-Gerüst zu vollem Branch-and-Price mit AC-2.1.8 im
Pricing ausbauen (der Lehrbuch-Weg). Höchste Eleganz und Exaktheit, höchster Aufwand,
unsicherster Zeitrahmen.

**Option D (pragmatisch) — SA-Repair.** Die einfache Form („Heimserie in eine Trip-Lücke
einschieben") ist **bereits implementiert** als Strategie 2 in
`generator_optimizer._greedy_fatigue_repair`. Wirkung (Produktion, Seed 42): worst_away je
nach SA-Budget ~14–24, typ. ~4 Teams > 13. Der greedy Einzelzug bleibt stecken, weil oft kein
Mid-Trip-Slot existiert, an dem der Gegner gleichzeitig frei + auswärts ist. Eine substanzielle
Verbesserung darüber hinaus = **gefensterter CP-SAT-LNS-Repair** (kleines Fenster pro Trip
freigeben, inkl. Gegner-Serien, lokal exakt lösen): tractable, deterministisch,
matchup-erhaltend, aber **ohne garantierten ≤13-Ausgang** (Kopplung kaskadiert über
Fenstergrenzen) und eine eigene, sorgfältig zu testende Implementierung.

---

## 8. Empfehlung (revidiert nach dem Option-A-Test)

Die Recherche hat den eleganten Ansatz korrekt identifiziert (HAP-Dekomposition), und das
HAP-Modell setzt AC-2.1.8 nachweislich durch. **Aber:** der Test in §5a zeigt, dass die
fertigen Muster nicht mit den fixen Matchup-Quoten kompatibel sind. Eine *direkte* elegante
Integration gibt es damit nicht — jeder strukturelle Weg, der die echten Matchups respektiert,
ist im Kern das volle APX-harte TTP:

- **`generator.py` global** (Serien + AC-2.1.8): intraktabel (7 Ansätze, §3).
- **HAP naiv** (Option A): infeasible wegen Matchup-Inkompatibilität (§5a).
- **Matchup-bewusste HAP / Branch-and-Price** (Option B/C): forschungsnah, mehrtägig, unsicher.

**Damit ist die Bedingung erfüllt, unter der ein pragmatischer Weg gerechtfertigt ist:** ein
direkt anwendbarer eleganter Fix existiert für das matchup-gebundene Produktionsproblem nicht.
Die einfache pragmatische Stufe (Heimserie einschieben) ist bereits aktiv (Option D); der
nächste echte Hebel ist der **gefensterte CP-SAT-LNS-Repair** — bounded und deterministisch,
aber ohne ≤13-Garantie und mit eigenem Implementierungs-/Testaufwand. Die strukturelle ≤13-Garantie
bleibt ein bewusst offenes Forschungs-Item (matchup-bewusste HAP / Branch-and-Price).

---

## 9. Umsetzung (2026-05-31): gefensterter LNS-Repair gebaut + integriert

Der in §8 empfohlene gefensterte CP-SAT-LNS-Repair wurde **implementiert, getestet und
integriert** (`generator_optimizer._lns_window_repair`), als opt-in Schritt nach der SA:

- Aktivierung: `GeneratorConfig.enable_lns_ac218_repair=True` (Default **False** →
  Produktionsverhalten unveraendert) bzw. `OptimizerConfig.enable_lns_ac218_repair`.
- Verfahren: pro Verletzer-Trip ein kleines Fenster (inkl. Gegner) + alle Serien des
  Teams freigeben, struktureller Gap-Constraint NUR fuer dieses Team, Stay-Close-Ziel,
  **global-monotone Akzeptanz** (uebernimmt nur, wenn #Teams>13 sinkt bzw. der globale
  worst sinkt; AC-2.1.9 wird nie verletzt).
- Garantien (Tests `tests/test_q10_lns_repair.py`): Matchup-Multiset bleibt exakt,
  keine Regression des worst_away, **deterministisch** (1-Worker, fester Seed).

**Gemessene Wirkung** (reale 2026-Instanz, Seed 42, 40k SA-Iter):

| | teams > 13 | Laufzeit-Aufschlag |
|---|---|---|
| ohne LNS (Produktion) | ~4–9 (run-abhaengig) | — |
| mit LNS | **3** | ~+10 s |

Es bleibt **kein** ≤13-Beweis: einzelne Teams (z. B. MIL @ 21 in einem Lauf) sind nicht
ohne Regression eines anderen reparierbar — die team-uebergreifende Kopplung (§2) kaskadiert
ueber Fenstergrenzen, exakt wie vorhergesagt. Das xfail bleibt daher bestehen; der LNS ist
eine **echte, sichere Reduktion** der Verletzungen, keine strukturelle Garantie. Die ≤13-
Garantie bleibt das offene Forschungs-Item (matchup-bewusste HAP / Branch-and-Price).

---

## Quellen (Recherche)

- Easton, Nemhauser, Trick — *The Traveling Tournament Problem: Description and Benchmarks*
  / *A Combined IP and CP Approach* (springer / researchgate)
- Irnich — *A new branch-and-price algorithm for the Traveling Tournament Problem*
  (ScienceDirect S0377221709007929; logistik.bwl.uni-mainz.de/files/2018/12/LM09-01.pdf)
- *The APX-hardness of the Traveling Tournament Problem* (arXiv:2308.14124)
- Hooker — *Planning and Scheduling by Logic-Based Benders Decomposition*
  (INFORMS Operations Research)
- *Feasibility of home–away-pattern sets for round robin tournaments*
  (ScienceDirect S0167637707001423)
- Eigene Messungen: `docs/REFACTOR_BACKLOG.md` Q10 (Updates 2026-05-31)
