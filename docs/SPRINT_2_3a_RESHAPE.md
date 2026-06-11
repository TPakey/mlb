# Sprint 2.3 Reshape — Schedule-Optimizer Core

**Datum der Entscheidung:** 2026-05-23
**Begründung:** Wir haben empirisch festgestellt, dass AC-2.1.8/9 sauber
durchzusetzen die Standard-CP-SAT-Architektur sprengt (vier Varianten
getestet, alle UNKNOWN nach 30 s oder marginale Repair-Wirkung). Die
akademische Literatur (Trick, Nemhauser, Easton) zeigt klar, dass das ein
**HAP-Decomposition mit Column Generation / Branch-and-Price** verlangt —
exakt die Methode, mit der die echten MLB-Pläne kommerziell erstellt werden.

## Neuer Scope

**Sprint 2.3 wird umbenannt zu Sprint 2.3a:** Schedule-Optimizer Core.

Alle ursprünglichen Sprint-2.3-Phasen ab Phase 2 (TV-Slots, Event-Friction,
Multi-Objective-SA, Pareto-Sampling, Profile-System, Dashboard) werden auf
**Sprint 2.3b** verschoben. Sprint 2.3b kann starten, sobald Sprint 2.3a
einen sauberen Generator liefert.

## Sprint 2.3a Inhalt

**Ziel:** Mathematisch sauberer Schedule-Generator, der alle harten
MLB-Constraints einschließlich AC-2.1.8/9 garantiert erfüllt — in der
Methode, die Trick/Nemhauser für die echte MLB verwenden.

**Architektur (HAP-Decomposition + Column Generation):**

1. **Pattern Generation (Phase A — bereits da):**
   Pro Team eigenes CP-SAT-Subproblem, das eine Home-Away-Pattern (HAP)
   generiert: 162 Tage mit Heim/Auswärts/Off-Markierung, AC-2.1.8/9
   garantiert eingehalten. Bereits implementiert in `src/two_phase_pacing.py`.

2. **Restricted Master Problem (RMP — neu):**
   LP über bereits generierte Patterns. Wählt pro Team genau ein Pattern,
   sodass:
   - Pair-Matching pro Tag (n_home = n_away)
   - Matchup-Quoten korrekt verteilbar
   Liefert duale Werte für das Pricing.

3. **Pricing Subproblem (neu — Erweiterung von Phase A):**
   Pro Team ein Subproblem, das ein neues Pattern mit *reduzierten Kosten
   < 0* generiert (basierend auf den dualen Werten des RMP). Falls keines
   mehr existiert → Pattern-Pool ist optimal.

4. **Column Generation Loop (neu):**
   ```
   while True:
       solve RMP (LP)
       dual_values = RMP.dual_values
       new_patterns = []
       for team in teams:
           pattern = solve_pricing(team, dual_values)
           if pattern.reduced_cost < 0:
               new_patterns.append(pattern)
       if not new_patterns: break
       add new_patterns to pattern_pool
   ```

5. **Branch-and-Price (neu — falls RMP fraktional):**
   Branching-Regeln über Pattern-Auswahl. Pro Branch ein neuer
   Column-Generation-Run.

6. **Series-Matching (neu — Phase B):**
   Nach gefundener Pattern-Auswahl: weise konkrete Gegner zu, cluster
   konsekutive Heim-Tage zu Heim-Series der richtigen Längen (2-4).

## Acceptance Criteria Sprint 2.3a

| # | Kriterium |
|---|---|
| AC-2.3a.1 | RMP solved auf 30-Team-Mini-Beispiel < 60 s |
| AC-2.3a.2 | Pricing-Subproblem liefert verbessertes Pattern oder beweist Optimalität |
| AC-2.3a.3 | Column-Generation-Loop terminiert in < 30 Min für volle MLB-Saison |
| AC-2.3a.4 | Resultierender Plan erfüllt AC-2.1.8 (max 13 konsek. Auswärtstage) zu 100 % |
| AC-2.3a.5 | Resultierender Plan erfüllt AC-2.1.9 (max 20 Spieltage in 21-Tage-Fenster) zu 100 % |
| AC-2.3a.6 | Resultierender Plan erfüllt alle Sprint-2.1-ACs (Spielzahl, Heim/Auswärts-Balance, Matchup-Quoten) |
| AC-2.3a.7 | Series-Matching liefert valide Length-2-3-4-Series gemäß Matchup-Quoten |
| AC-2.3a.8 | Reproduzierbarkeit: gleicher Seed → identische Lösung |

## Aufwand-Realistisch

| Block | Aufwand |
|---|---|
| Pattern-Generation (Phase A) | ✅ fertig |
| RMP-Skelett + LP-Solver-Integration | 0,5 Tag |
| Pricing-Subproblem-Erweiterung | 0,5 Tag |
| Column-Generation-Loop | 0,5 Tag |
| Konvergenz-Tuning + Pattern-Cleanup | 1 Tag |
| Branch-and-Price (falls fraktional) | 1–2 Tage |
| Series-Matching (Phase B) | 1 Tag |
| Tests + Validierung | 1 Tag |
| Review + Doku | 0,5 Tag |
| **Total realistisch** | **5–7 Tage** |

Wir liefern in dieser Cowork-Session den **funktionsfähigen Kern** (Phase A
+ RMP-Skelett + erste Pricing-Iteration). Skalierung und Branch-and-Price
folgen iterativ in weiteren Sessions.

## Was nach Sprint 2.3a kommt — Sprint 2.3b

Ursprünglicher Sprint-2.3-Inhalt: TV-Slot-Score, Local-Event-Friction,
Multi-Objective-SA, ε-Constraint, Pareto-Sampling, Profile-System (named +
free), Dashboard-Panel. Diese Phasen können alle auf dem neuen sauberen
Generator-Output arbeiten und sind dann viel einfacher zu validieren (weil
die Achsen wie "Fatigue-Score" auf ehrlichen Daten basieren).

## Quellen — akademische Grundlage

- [Easton, Nemhauser, Trick 2004: Solving the Traveling Tournament Problem](https://link.springer.com/chapter/10.1007/978-3-540-45157-0_6)
- [Trick: Adventures in Sports Scheduling](https://www.cs.cmu.edu/~ACO/dimacs/trick.html)
- [Barnhart, Johnson, Nemhauser et al.: Branch-And-Price: Column Generation for Huge Integer Programs](https://pubsonline.informs.org/doi/10.1287/opre.46.3.316)
- [Rasmussen, Trick: Round Robin Scheduling — Survey](http://www.dcc.ic.uff.br/~celso/artigos/sports-scheduling.pdf)
- [Springer: First-Break-Then-Schedule HAP Sets](https://link.springer.com/article/10.1007/s10951-022-00734-w)
