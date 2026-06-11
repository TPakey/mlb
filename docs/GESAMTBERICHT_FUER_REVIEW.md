# MLB Logistics Optimizer — Gesamtbericht für Review

**Stand:** 2026-05-31 (Sprint 2.12) · **Status:** Forschungsprototyp mit Produktreife-Anspruch
**Zweck dieses Dokuments:** vollständige, ehrliche Standortbestimmung des Systems für ein
externes Review. Ersetzt die frühere Fassung, die noch die inzwischen widerlegten
Review-Annahmen (C1/C2/C3) als offene Defekte führte — diese sind adressiert und werden
hier korrekt dargestellt.

---

## 1. Executive Summary

Der MLB Logistics Optimizer baut einen mathematisch optimierten Alternativplan für eine
volle MLB-Regulärsaison (30 Teams, 2.430 Spiele) und bewertet ihn über acht Zieldimensionen.
Er minimiert Reisedistanzen, hält die sportlichen und CBA-Regeln ein und stellt
Entscheidungsträgern eine **Pareto-Front** alternativer Pläne sowie eine **What-if-Engine**
für schnelle Szenario-Analysen bereit.

**Kernergebnisse:**

- Voller Saisonplan deterministisch in ~15–35 s (CP-SAT-Feasibility ~0,2 s + Simulated
  Annealing). Reisedistanz konvergiert über alle getesteten Seeds auf **~2,07–2,17 Mio km**.
- **AC-2.1.9** (max. 20 Spieltage je 21-Tage-Fenster) wird **strukturell garantiert** —
  0 Verletzungen über alle vier verifizierten Seeds.
- **AC-2.1.8** (max. 13 „days away from home") wird unter der korrekten CBA-Definition
  weich durchgesetzt und stark reduziert, aber bei der realen Saison-Dichte nicht garantiert
  auf ≤13 eliminiert. Dieser Status ist ehrlich dokumentiert, mit einer gründlichen
  Analyse, warum eine strukturelle Garantie ein eigenes Forschungsproblem ist (Abschnitt 6).
- Revenue-/TV-Modell auf **−1,40 %** zur Sportico-Liga-Summe kalibriert (Toleranz ±10 %).
- Code sauber und getestet: ~297 Tests grün, 2 dokumentierte `xfail`; `pyflakes` sauber im
  aktiven Pfad; deterministisch reproduzierbar (`num_search_workers=1` + feste Seeds).

---

## 2. Was das System leistet

Eine MLB-Saison umfasst 30 Teams × 162 Spiele = 2.430 Spiele über ~186 Kalendertage. Die
Aufgabe ist ein Constraint-Optimierungsproblem mit harten Regeln (Serienstruktur,
Heim/Auswärts-Balance, All-Star-Break, CBA-Fatigue-Limits) und konkurrierenden weichen
Zielen (Reise, Gate-Revenue, TV-Attraktivität, Spieler-Fatigue, lokale Event-Konflikte).

Das System liefert:

1. **Einen optimierten Basisplan** (CP-SAT + Simulated Annealing).
2. **Eine Pareto-Front** nicht-dominierter Alternativen über acht Dimensionen, sodass
   Entscheider Trade-offs explizit sehen statt einer einzelnen Black-Box-Lösung.
3. **What-if-Analysen** in unter zwei Sekunden (Serie erzwingen, Stadion-Blackout,
   Plan-Vergleich) mit Validitäts-Checks.
4. **Disruption-Handling** (z. B. Hurricane-Szenario) über drei Reparatur-Strategien.
5. **Schnittstellen**: CLI (`python -m src.main`), interaktives D3-Dashboard und ein
   REST-API-Skelett (`tools/api.py`) für die Integration in MLB-IT-Systeme.

---

## 3. Architektur

Der Hauptpfad ist eine zweistufige Pipeline; die akademische HAP/Column-Generation-Variante
existiert parallel als verifiziertes Backup (siehe `docs/ARCHITECTURE_DECISION.md`).

**Stufe 1 — CP-SAT (Google OR-Tools).** Jede Serie wird als Intervall mit fester Länge
platziert, NoOverlap pro Team verhindert Doppelbelegungen. Periodische Break-Days alle 21
Tage werden in die Serien-Domains aufgenommen — damit ist AC-2.1.9 per Pigeonhole-Argument
strukturell garantiert. Der All-Star-Break wird als sperriges Fenster behandelt. CP-SAT
findet einen feasiblen Plan deterministisch in ~0,2 s.

**Stufe 2 — Simulated Annealing.** Auf dem feasiblen Plan minimiert ein SA-Verfahren die
Gesamt-Reisedistanz. Die Energiefunktion kombiniert km mit einer Fatigue-Penalty
(λ = 1.000.000), die AC-Verletzungen praktisch unmöglich akzeptiert, plus einem
deterministischen AC-2.1.8-Pre/Post-Repair, der zu lange Road-Trips gezielt aufbricht. Die
km-Berechnung läuft inkrementell pro Team (bit-identisch zur Vollberechnung) für
Determinismus und Geschwindigkeit.

**Pareto-Explorer.** Mehrere SA-Läufe über sechs benannte Profile plus zufällige
Mischprofile (Dirichlet-Sampling) erzeugen eine Menge von Plänen; ein Dominanz-Filter
liefert die Pareto-Front über die acht Dimensionen Reise, Revenue, Fatigue, Away-Streak,
Off-Day-Varianz, TV-Slot, Event-Friction, Constraint-Violations.

**What-if & Disruption.** Lokale Re-Planung ohne CP-SAT-Neustart (< 2 s) mit
ParetoBundle-Deltas über alle acht Dimensionen und expliziten Warnungen bei
Constraint-Risiken.

**Subpackage-Struktur (A20/A21, 2026-05-31).** `column_generation.py` (~850 LOC) und
`whatif.py` (~890 LOC) wurden in die Subpackages `src/colgen/` (patterns/rmp/pricing/
engine/hap) bzw. `src/whatif_core/` (types/helpers/force/blackout/compare/impact) aufgeteilt;
die Original-Dateien bleiben als dünne öffentliche Fassaden mit unveränderten Importpfaden.

---

## 4. Kennzahlen (empirisch, voller Saison-Lauf 2026)

**Multi-Seed-Verifikation** (voller `generate()`-Pfad, korrigierte AC-2.1.8-Definition,
1-Worker, Stand nach dem A-6-Break-Day-Fix):

| Seed | Status  | Reise-km   | AC-2.1.9 (worst_off / Verletzer) | AC-2.1.8 (worst_away / Verletzer) |
|------|---------|------------|----------------------------------|------------------------------------|
| 42   | OPTIMAL | ~2,10 Mio  | 20 / **0** ✓                     | 20 / 6 Teams                       |
| 7    | OPTIMAL | ~2,12 Mio  | 20 / **0** ✓                     | 23 / 2 Teams                       |
| 11   | OPTIMAL | ~2,17 Mio  | 20 / **0** ✓                     | 17 / 5 Teams                       |
| 17   | OPTIMAL | ~2,07 Mio  | 20 / **0** ✓                     | 23 / 6 Teams                       |

**Revenue/TV.** Das Gate-Revenue-Modell (Sportico/Statista 2024-kalibriert) liegt **−1,40 %**
zur Liga-Summe (Toleranz ±10 %). Division-Rival-Bonus stapelt korrekt multiplikativ mit dem
Marquee-Faktor (z. B. BOS@NYY = 1,12 × 1,05 = 1,176). TV-Slots werden über ein
Erwartungswert-Modell (Daypart-Mix je Wochentag) bewertet, das Sunday-Night-Slots realistisch
vergibt.

**Pareto-Front.** Liefert mehrere nicht-dominierte Pläne (Ziel ≥7) in ~2,2 s; bei
ungünstigen Seeds greift ein dokumentierter Least-Bad-Fallback (`degraded`/`diagnostic`),
statt zu crashen.

---

## 5. Datengrundlage

- **Teams & Stadien** (`data/teams.json`): 30 Teams mit Koordinaten, Zeitzonen und
  Stadion-Metadaten, kuratiert auf Basis der MLB Stats API. **OAK/Athletics 2026 verifiziert
  (2026-05-31):** Heimstätte ist der **Sutter Health Park, West Sacramento, CA**
  (lat 38,5806 / lon −121,5133, Pacific Time) — das zweite von voraussichtlich drei
  Interimsjahren in Sacramento vor dem geplanten Umzug nach Las Vegas. *Modell-Hinweis:* Die
  A's tragen 2026 sechs ihrer 81 Heimspiele (8.–14. Juni) im Las Vegas Ballpark aus; das
  Single-Venue-Modell bildet das bewusst nicht ab (vernachlässigbar für die
  Liga-Gesamtdistanz, dokumentiert).
- **Revenue/TV** (`revenue_model.json`, `tv_slots.json`): Sportico/Statista-kalibriert (2024),
  mit explizitem Kalibrier-Hinweis im JSON.
- **Events/Wetter** (`local_events.json`, `soft_factors.json`): kuratierte, datierte Listen
  (siehe `docs/LOCAL_EVENTS_RESEARCH.md`).
- **Matchup-Quoten**: aus einer realen Vorjahres-Saison (`mlb_schedule_2024.json`) extrahiert,
  garantiert korrekte Paarungs-Häufigkeiten und Heim/Auswärts-Balance.

---

## 6. CBA-Constraints: ehrlicher Status

### AC-2.1.9 — max. 20 Spieltage je 21-Tage-Fenster: **strukturell garantiert ✓**

Über die periodischen Break-Days im CP-SAT (max_gap = 21) per Pigeonhole sichergestellt;
0 Verletzungen über alle vier verifizierten Seeds. Ein in Sprint A-6 gefundener Restbug (die
SA durfte Serien auf strukturell verbotene Off-Days schieben) wurde behoben.

### AC-2.1.8 — max. 13 „days away from home": **weich durchgesetzt, offene Limitation**

Definition (korrigiert in Sprint 2.7, `docs/CBA_DEFINITIONS.md`): Eine Road-Trip ist die
Spanne vom ersten bis zum letzten Auswärtsspiel; **Off-Days mittendrin zählen mit**, nur ein
Heimspiel beendet sie. Unter dieser strengeren, korrekten Definition bleiben im realen
2026-Plan typischerweise einige Teams über dem 13-Tage-Limit (worst-case ~17–24 Tage,
2–6 Teams je nach Seed). Die SA-Penalty plus deterministischer Repair reduziert die
Verletzungen deutlich, eliminiert sie aber nicht garantiert.

**Warum keine einfache strukturelle Garantie?** Das wurde 2026-05-31 gründlich untersucht
(`docs/Q10_ANALYSE_UND_RECHERCHE.md`). Das Problem ist das gut erforschte, **APX-harte
Traveling Tournament Problem**. Sieben CP-SAT-Standardansätze (monolithische Gap-Formulierung,
Gap + virtueller Break-Anker, Drei-Phasen-Decomposition, globales Fix-and-Optimize,
FIXED_SEARCH, Automaton/Regular-Constraint, Automaton + lokale Domain) sind im
1-Worker-Modus allesamt intraktabel (UNKNOWN). Die Härte ist intrinsisch in der
team-übergreifenden Kopplung (jede Serie ist Heim für ein und Auswärts für das andere Team),
nicht eine Frage der Encoding-Größe.

Die literatur-bestätigte elegante Lösung ist Dekomposition (Branch-and-Price bzw.
„first-break-then-schedule" über Home-Away-Patterns). Diese ist in `colgen.solve_global_hap`
bereits gebaut und setzt AC-2.1.8 **by construction** durch (verifiziert worst_away = 13) —
allerdings in einer *relaxierten* Variante mit emergenten Matchups. Mit den fixen
Matchup-Quoten gekoppelt ist sie infeasible (173/811 Serien ohne musterkonformen Tag); eine
matchup-bewusste HAP-Generierung ist im Kern wieder das volle TTP.

**Was produktiv verfügbar ist:** ein optionaler gefensterter CP-SAT-LNS-Repair
(`enable_lns_ac218_repair`, Default aus). Er löst pro zu langem Road-Trip ein kleines
CP-SAT-Teilproblem mit Stay-Close-Ziel und global-monotoner Akzeptanz, senkt die Zahl der
Teams über dem Limit messbar (in Messungen von ~4–9 auf 3), bleibt 1-Worker-deterministisch
und matchup-erhaltend — liefert aber **keinen ≤13-Beweis**.

**Sichtbar gemacht durch:** `test_AC_2_1_8_realer_generator_haelt_konsekutive_away_limit`
(`xfail` mit ausführlichem Reason) und die Multi-Seed-Tabelle in Abschnitt 4.

---

## 7. Code-Qualität & Tests

- **~297 Tests grün, 2 dokumentierte `xfail`** (AC-2.1.8-Real-Generator, AC-2.3.1
  Pareto-≥7), beide ehrlich begründet. Die CP-SAT-schweren `slow`-Tests laufen via CI über
  das 45-s-Sandbox-Limit hinaus.
- **Property-Based-Tests** (`hypothesis`, bis 200 Examples): u. a. dass beide
  AC-2.1.8-Implementierungen übereinstimmen und der Repair nie eine neue Verletzung erzeugt.
- **Determinismus**: `num_search_workers=1` + feste Seeds → bit-identische Ergebnisse
  (AC-2.1.11). Dependencies in `requirements.txt` gepinnt.
- **Hygiene**: `pyflakes` im aktiven `src/`-Pfad sauber (ein dokumentierter Re-Export);
  `print()` durch `logging` ersetzt; Alt-Code isoliert unter `src/legacy/`.
- **Audit-Historie**: zwei unabhängige Audit-Runden (A-1…A-6, QA-Audit Q1–Q9) plus diese
  Q10-Analyse; Befunde im Code gefixt oder mit klarer Begründung als Folge-Item dokumentiert
  (`docs/REFACTOR_BACKLOG.md`).

---

## 8. Bewusst offene Limitationen (vollständig)

1. **AC-2.1.8-Garantie** — der zentrale offene Punkt (Abschnitt 6). Weiche Durchsetzung +
   optionaler LNS-Repair statt struktureller ≤13-Garantie. Pfad zur Lösung dokumentiert
   (matchup-bewusste HAP / Branch-and-Price).
2. **Pareto-≥7 bei ungünstigen Seeds** — Least-Bad-Fallback statt harter Garantie
   (`xfail`, mit Laufzeit-Diagnose).
3. **Revenue-Kalibrierung 2024** — jährlich nach Liga-Schluss neu zu eichen (Hinweis im JSON).
4. **Single-Venue-Modell** — die sechs OAK-Heimspiele in Las Vegas 2026 sind nicht
   abgebildet (vernachlässigbar, dokumentiert).
5. **REST-API als Skelett** — Endpoints funktional verdrahtet; Auth, Job-Queue für lange
   Solver-Läufe und Persistenz sind als TODO markiert.

---

## 9. Empfohlene nächste Schritte

1. **AC-2.1.8 strukturell** (eigener Forschungs-Sprint): matchup-bewusste HAP-Generierung
   oder Branch-and-Price mit AC-2.1.8 im Pricing — der einzige Weg zur echten ≤13-Garantie.
2. **CI/CD** härten: `pytest` + `mypy` + `pyflakes` als Pflicht-Gate je PR; die `slow`-Tests
   dort verbindlich laufen lassen.
3. **Stakeholder-Workshop**: die Pareto-Front mit echten MLB-Ops durchgehen — ggf. fehlt
   eine Dimension oder wird doppelt gewertet.
4. **Daten-Refresh-Routine**: jährliche Neukalibrierung von `revenue_model.json` als Skript.
5. **REST-API produktiv** härten (Auth, asynchrone Jobs, Persistenz).

---

## Anhang — Verweise

- `docs/Q10_ANALYSE_UND_RECHERCHE.md` — vollständige AC-2.1.8-Analyse + Literatur-Recherche
- `docs/CBA_DEFINITIONS.md` — verbindliche AC-2.1.8/9-Definitionen
- `docs/REFACTOR_BACKLOG.md` — Q10 + A20/A21 (erledigt) + offene Architektur-Items
- `docs/ARCHITECTURE_DECISION.md` — Haupt- vs. Backup-Pipeline
- `docs/SPRINT_PLAN_FIXES.md` — Sprint-Plan 2.7–2.12 (Mapping Finding → Sprint)
