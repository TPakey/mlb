# Refactor-Backlog (bewusst aufgeschobene Architektur-Items)

**Stand:** 2026-05-28 (Sprint A-5)

Diese Items wurden im Audit identifiziert, ihre Umsetzung jedoch bewusst
aufgeschoben, weil sie risikoreiche Massen-Refactors kurz vor der MLB-
Übergabe darstellen würden — und weil sie weder Korrektheit noch Sicherheit
beeinflussen, sondern reine Wartbarkeit.

---

## A20 — `src/column_generation.py` (~850 LOC) aufgeteilt ✓ ERLEDIGT (2026-05-31)

**Umsetzung:** In das Subpackage `src/colgen/` aufgeteilt — `patterns.py`
(Pattern + pacing_to_pattern), `rmp.py` (Restricted Master Problem, GLOP),
`pricing.py` (Pricing-Subproblem, CP-SAT), `engine.py` (Worker, ColumnGenerationLog,
run_column_generation), `hap.py` (GlobalHAPResult, solve_global_hap), plus
`__init__.py` mit Re-Export.

`src/column_generation.py` bleibt als **dünne öffentliche Fassade** (re-exportiert
aus `colgen`) — bestehende Importe `from src.column_generation import X`
funktionieren unverändert. (Hintergrund: Die Sandbox durfte die alte Datei nicht
löschen, daher Fassade statt gleichnamigem Package-Verzeichnis — funktional
äquivalent.)

**Verifikation:** alle 25 `test_sprint_2_3a`-Tests grün; `pyflakes src/colgen/
src/column_generation.py` sauber; `compileall src/` ok.

**Hinweis:** eine 5-Byte `src/colgen/_probe.txt` (Schreibtest-Artefakt) konnte aus
der Sandbox nicht gelöscht werden — harmlos (keine `.py`), lokal entfernbar.

---

## A21 — `src/whatif.py` (~890 LOC) aufgeteilt ✓ ERLEDIGT (2026-05-31)

**Umsetzung:** In das Subpackage `src/whatif_core/` aufgeteilt — `types.py`
(DimensionDelta, WhatIfContext, WhatIfResult), `helpers.py` (DIMENSION_LABELS +
7 Privatfunktionen: _build_deltas, _find_free_slot, _find_series_for_matchup,
_flag_constraint_violations, _move_games_to_date, _occupied_days, _replace_games),
`force.py` (whatif_force_series), `blackout.py` (whatif_blackout), `compare.py`
(whatif_compare), `impact.py` (TeamImpact + analyze_team_impact), plus `__init__.py`
mit Re-Export. Schichtung azyklisch: types ← helpers ← {force, blackout, compare,
impact}.

`src/whatif.py` bleibt als **dünne öffentliche Fassade** (re-exportiert aus
`whatif_core`, inkl. der von Tests importierten Privat-Helfer) — bestehende
Importe funktionieren unverändert.

**Zwei Anpassungen waren nötig** (vom Backlog vorgesehen, „Tests müssten beim
Re-Export aktualisiert werden"): (1) Inline-Imports `from .travel/.revenue/...`
→ `from ..travel/...` (Modul liegt eine Ebene tiefer). (2) Die 13 Test-Patches
`@patch("src.whatif.compute_pareto_bundle")` zeigen jetzt auf das jeweilige
Submodul (`src.whatif_core.{force,blackout,compare}.compute_pareto_bundle`), da
der Patch sonst nach dem Split nicht mehr greift.

**Verifikation:** alle 86 Tests (test_whatif 46 + test_whatif_demo 40) grün;
`pyflakes src/whatif_core/ src/whatif.py` sauber; `compileall src/` ok.

**Hinweis:** Wie A20 bleibt `src/whatif.py` eine Fassade statt eines gleichnamigen
Package-Verzeichnisses (Sandbox durfte die Originaldatei nicht löschen) — funktional
äquivalent; der Implementierungs-Code liegt vollständig in `src/whatif_core/`.

---

## Empfohlene Reihenfolge

1. **A20 zuerst** — kleineres Risiko, klarere Schnittstellen (RMP/Pricing
   sind algorithmische Komponenten mit wenig Cross-Kopplung).
2. **A21 danach** — auf der gleichen Re-Export-Mechanik. Wenn A20 funktioniert,
   ist A21 mechanisch dasselbe Muster.

Beide Refactors sollten in einem separaten Sprint mit dediziertem
Test-Lauf nach jedem Move passieren — nicht im Audit-Fix-Block.

---

## Q10 — AC-2.1.8 strukturell durchsetzen ✓ GESCHLOSSEN (2026-06-09, obsolet)

> **GESCHLOSSEN durch Re-Klassifikation (2026-06-09).** Volltext-Verifikation des CBA
> (`regulations/FINDING_AC-2.1.8_vs_CBA.md`): „13 days away" ist **kein** CBA-Erfordernis
> (nicht in Article V; das harte Muss ist V(C)(12) = AC-2.1.9/≤20, bereits strukturell
> garantiert). Jonas hat bestätigt: AC-2.1.8 = **weiches** Qualitätsziel. Eine strukturelle
> ≤13-Garantie ist damit gegenstandslos. `compliance.py`: AC-2.1.8 = `severity="soft"`;
> xfail-Test umgewidmet (`test_AC_2_1_8_ist_weiches_qualitaetsziel_...`). Branch-and-Price
> NICHT mehr für ≤13 nötig (nur optional für green-field, Sprint 5.4). Analyse unten bleibt
> als Forschungs-Dokumentation.

**Stand:** 2026-05-29 (QA-Audit). Schwere: ~~HOCH~~ → **obsolet** (s. o.).

**Problem:** Der Produktionsgenerator hält AC-2.1.8 (max 13 „days away from home")
nicht strukturell ein. Gemessen am realen 2026-Plan (Seed 42): ~4 Teams über dem
Limit, worst-case 20 Tage. Aktuell nur weiche Durchsetzung (SA-Penalty + greedy
repair), die die Verletzungen nicht eliminiert. Test ist als `xfail` markiert
(`tests/test_fatigue_constraints.py::test_AC_2_1_8_realer_generator_haelt_konsekutive_away_limit`).

**Fortschritt (QA 2026-05-29):** Eine **verifiziert-sounde** CP-SAT-Formulierung
existiert bereits — `generator._add_ac_2_1_8_gap_constraints` (Gap/Nachfolger
auf den Heim-Serien-Starts, ~23k Booleans). Korrektheit gegen ein Brute-Force-
Orakel abgesichert (315 Zufallsinstanzen, 0 Verletzungen; Repo-Test
`tests/test_qa_audit_fixes.py::test_ac218_gap_formulation_is_sound`). Die
**Korrektheits-Frage ist damit gelöst** — der frühere Off-by-one (`+14` statt
exklusivem End `+13`) ist behoben.

**Offen ist nur noch die Tractability:** Mit All-Star-Break löst die volle Saison
nur intermittierend (1-Worker deterministisch UNKNOWN/36 s; 8-Worker mal
OPTIMAL/13 s, mal UNKNOWN; Warm-Start-Decomposition half nicht stabil). Deshalb
ist der Helfer im Produktionspfad bewusst NICHT verdrahtet — eine intermittierend
infeasible Generierung wäre für MLB inakzeptabel. Details:
`docs/QA_AUDIT_2026-05-29.md` Q10. (Verworfen: Cover-Matrix, ~140k Booleans,
UNKNOWN/40 s.)

**Verbleibender Plan (Tractability):**
1. Stärkere Propagation: redundante Constraints, oder ein Automaton-/Reservoir-
   Encoding statt der O(Serien²)-Nachfolger-Bools.
2. Echte Decomposition: Saison-Hälften um den All-Star-Break unabhängig lösen.
3. Manuelle Search-Strategy (`solver.parameters.search_branching`), die zuerst
   die Serien-Starts fixiert.
4. Alternativ/ergänzend: Greedy-Repair in `generator_optimizer` erweitern, der
   aktiv Heimserien in zu lange Road-Trips einschiebt (statt nur gleichlange
   Serien zu tauschen).

**Akzeptanzkriterium:** voller Pfad MIT All-Star-Break ZUVERLÄSSIG (auch
1-Worker, mehrere Seeds) OPTIMAL/FEASIBLE in akzeptabler Zeit, worst_away ≤ 13.
Dann `_add_ac_2_1_8_gap_constraints` verdrahten und das xfail entfernen.

**Aufwand:** mittel-hoch (Korrektheit erledigt, nur noch Solver-Performance) —
eigener Sprint, nicht im Audit-Block.

### Update 2026-05-31 — Decomposition implementiert, Tractability weiter offen

Schritt 2 (Decomposition) wurde **gebaut und getestet**, nicht nur skizziert:

- **Virtueller Break-Heimstand:** pro Team ein fixes Heim-Intervall über die
  All-Star-Break-Tage. Da während des Breaks kein Team auswärts ist, überspannt
  keine Road-Trip den Break → AC-2.1.8 zerfällt sauber in zwei unabhängige
  Halbsaison-Probleme; der Break-Anker ist Schluss-Anker der ersten und
  Eröffnungs-Anker der zweiten Hälfte.
- **Drei-Phasen-Solve** (`generator._solve_ac218_decomposed`,
  `_solve_one_phase`): Phase 0 gap-freies Skelett → Hälften-Zuordnung; Phase 1
  erste Hälfte frei + Gap-Constraints; Phase 2 zweite Hälfte frei. Der Helfer
  `_add_ac_2_1_8_gap_constraints` ist um halb-lokale Grenzen (`day_lo`/`day_hi`)
  erweitert. Aktiviert über `GeneratorConfig.enforce_ac218_structural=True`
  (Default False, verhaltens-identisch wenn aus; `test_generator` +
  `test_qa_audit_fixes` bleiben grün).

**Ergebnis: Tractability NICHT gelöst.** Gemessen am realen 2026-Instance
(811 Serien, Seed 42, `LocalFileAdapter`):

| Ansatz | Worker | Zeit | Ergebnis |
|---|---|---|---|
| Monolithisch + Break-Anker | 1 | 35 s | **UNKNOWN** |
| Decomposition `generate()` | 1 | 12 s/Phase | **UNKNOWN** (Phase 1) |
| Decomposition `generate()` | 4 | 13 s/Phase | **UNKNOWN** (Phase 1) |
| Decomposition, Phase 1 isoliert | 4 | 35 s | **UNKNOWN** |
| Globales Fix-and-Optimize ±K | 1 | — | K=6 INFEASIBLE, K=10 UNKNOWN/33 s |
| FIXED_SEARCH (Skelett-first) | 1 | 36 s | UNKNOWN |

Phase 0 (gap-frei) löst zuverlässig in ~0.2 s. Die **Halbierung des Horizonts
reicht nicht** — die Härte stammt aus der team-übergreifenden Kopplung der
disjunktiven Nachfolger-Formulierung (jede Serie ist Heim für ein, Auswärts für
das andere Team), nicht aus der Saisonlänge. Auch eine einzelne Hälfte (477
Serien) bleibt nach 35 s UNKNOWN.

**Schlussfolgerung (Decomposition):** Die Gap-/Nachfolger-Formulierung ist —
monolithisch wie dekomponiert — für den 1-Worker-Produktionspfad nicht tragfähig.

### Update 2026-05-31 (2) — Automaton/Regular-Constraint erprobt → ebenfalls UNKNOWN

Die fundamental andere Encodierung wurde **prototypisch gebaut und gemessen**:
pro Team ein Heim-Tages-Indikator `day_state[d]` (kanalisiert aus den
Heim-Serien) plus `AddAutomaton`, der einen Lauf von 14 Nicht-Heim-Tagen verbietet
(äquivalent zur Fenster-Summe `sum(day_state[d:d+14]) >= 1`, aber mit dem
stärkeren Regular-Propagator). Hinweis: „kein 14er-Lauf" ist eine **konservative,
sound** Verschärfung von AC-2.1.8 (Off-Days an Trip-Rändern zählen mit; garantiert
Spanne ≤ 13).

Messung (reale Instanz, 811 Serien, Seed 42, 1-Worker):

| Encodierung | Build | Channel-Bools | Solve | Ergebnis |
|---|---|---|---|---|
| `AddAutomaton` über day_state | 2.7 s | ~150 000 | 22 s | **UNKNOWN** |
| `AddAutomaton` + ±14-Domain + Warm-Hint | 0.4 s | ~23 000 | 25 s | **UNKNOWN** |

Der Automaton propagiert zwar stark, aber die **Kanalisierung der
Tages-Indikatoren aus den Serien-Intervallen kostet ~150k reified Booleans** —
exakt der Blow-up der früher verworfenen Cover-Matrix. Die zweite Zeile zeigt das
Entscheidende: selbst wenn man den Channel per lokaler ±14-Tage-Domain-Einschränkung
(plus Warm-Start aus dem gap-freien Skelett) auf **23k Bools** drückt — also die
Größe der schlanken Gap-Formulierung —, bleibt der Solve UNKNOWN. **Die Härte
liegt nicht in der Bool-Anzahl, sondern ist intrinsisch in der Kombinatorik**
(Round-Robin-Scheduling mit per-Team-Road-Trip-Limit und team-übergreifender
Kopplung: jede Serie ist Heim für ein, Auswärts für das andere Team). Die schlanke
Gap-Formulierung propagiert zu schwach, die Fenster/Automaton-Form ist zu groß —
und die Mitte (gleiche Größe, stärkerer Propagator) löst trotzdem nicht.

**Damit ist Q10 über sechs unabhängige Ansätze als mit CP-SAT-Standardmitteln
(1-Worker) nicht tragfähig belegt:** monolithische Gap, Gap+Break-Anker,
Drei-Phasen-Decomposition, globales Fix-and-Optimize, FIXED_SEARCH,
Automaton/Window. Die Korrektheit/Soundness aller Formulierungen ist gesichert —
es scheitert ausschließlich an der Solver-Tractability.

**Empfohlener nächster Schritt:** die **pragmatische Route** — den
deterministischen SA-Repair in `generator_optimizer` erweitern, sodass er aktiv
Heimstände in zu lange Road-Trips einschiebt. Das reduziert die realen
Verletzungen weiter (heute worst ~14–20), bleibt 1-Worker-deterministisch und
zuverlässig, liefert aber keinen ≤13-Beweis → das xfail bliebe. Eine echte
strukturelle Garantie würde fortgeschrittene Methoden außerhalb des
CP-SAT-Standardrepertoires erfordern (z. B. Branch-and-Price / Spalten­generierung
mit AC-2.1.8 im Pricing, oder einen dedizierten LNS-Repair-Solver).

Das xfail bleibt. Die Decomposition-Scaffolding (default-off) ist erhalten; der
Automaton-Prototyp ist als Negativ-Ergebnis dokumentiert (nicht im `src/`-Pfad).
