# Audit A1 — `add_offday_slots`-Aktivierung (Status)

**Datum:** 2026-05-28 (Sprint A-2)

## Befund (Audit)

`src/generator_constraints.add_offday_slots` existierte bereits im Repo, wurde
aber von keinem Modul aufgerufen — toter Code, der im Docstring eine
strukturelle AC-2.1.8-/AC-2.1.9-Durchsetzung versprach.

## Was versucht wurde

1. **Doku-Korrektur ✓** — Der irreführende AC-2.1.8-Beweis (gilt nur unter der
   alten Definition, in der Off-Days den Auswärts-Streak brechen) wurde aus dem
   Modul-Docstring entfernt; verbleibende Aussage: AC-2.1.9 strukturell + max
   `max_gap-1` konsekutive Play-Days.
2. **Verdrahtung im Hauptpfad ✗** — `add_offday_slots(...)` wurde in
   `generator.generate()` aufgerufen, sowohl alleine (ohne periodische Breaks)
   als auch parallel zu ihnen.
3. **Domain-Optimierung ✓ teilweise** — `NewIntVarFromDomain(FromValues(...))`
   wurde durch `NewIntVar(0, total_days-1)` + separate
   `model.Add(off_start != bd)`-Constraints ersetzt, was die initiale
   Variablendarstellung deutlich verkleinert.

## Empirisches Resultat

CP-SAT findet auch nach **40+ Sekunden** keine erste feasible Lösung für die
volle 2026-Saison (Seed 42), selbst mit `max_gap=21` (das *lockerste* Setting,
das nur AC-2.1.9 strukturell erzwingt). Vergleich: ohne `add_offday_slots`
findet CP-SAT in **2–8 Sekunden** ein OPTIMAL.

Die Constraint-Propagation über 30 Teams × 24 Off-Day-IntVars
(720 zusätzliche Variablen) mit Order-, Max-Gap- und Boundary-Constraints
plus NoOverlap mit allen Series-Intervallen pro Team ist im aktuellen Modell
zu schwer.

## Konsequenz für Sprint A-2

`add_offday_slots` bleibt im Repo (mit korrigierter Doku und der
Domain-Optimierung), aber **nicht aktiviert** im Hauptpfad. Die im Audit
beschriebene Erwartung („wenn aktiviert, schließt das AC-2.1.9 strukturell")
hat sich empirisch nicht bestätigt — die Aktivierung verschlechtert die
Performance um Größenordnungen, statt sie zu verbessern.

Die ursprüngliche **Audit-A1-Erkenntnis bleibt richtig**: Toter Code mit
irreführender Doku war ein Problem. Die Doku-Korrektur ist umgesetzt; eine
funktionsfähige Aktivierung erfordert tiefere Solver-/Constraint-Arbeit
(eigene Search-Strategy, andere Decomposition, evtl. Lazy-Constraints), die
über den Umfang eines Audit-Fix-Sprints hinausgeht.

## Pfad nach vorne (dokumentiert für späteren Sprint)

1. **Manuelle Search-Strategy:** `solver.parameters.search_branching = ...`
   konfigurieren, damit CP-SAT zuerst Series-Vars belegt und Off-Days erst
   anschließend füllt.
2. **Reduzierte Off-Day-Anzahl:** Statt aller K = total_days - n_games
   Off-Days nur die für AC-2.1.9 strikt nötigen ⌈total_days/21⌉ pro Team
   modellieren.
3. **Disjunktive Decomposition:** Off-Days und Series in zwei separaten
   Solver-Aufrufen (zuerst Series, dann Off-Days füllen die Lücken).
4. **Periodische Break-Days als „warmer Hint":** Die bestehende periodische
   Break-Day-Lösung als Initial-Assignment in den Solver geben.

Bis dahin: AC-2.1.9 wird strukturell weiterhin über die periodischen
Break-Days (`_periodic_break_days(total_days, max_gap=21)`) garantiert, mit
empirisch beobachteter Rest-Toleranz (~2 Teams mit worst_off=21 bei einigen
Seeds — innerhalb des dokumentierten Risiko A des Plans).
