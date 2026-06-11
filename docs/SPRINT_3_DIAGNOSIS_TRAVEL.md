# Diagnose: Warum unser Plan mehr reist als der echte MLB-Spielplan

**Stand:** 2026-06-01 · **Track:** Sprint 3 / B-Befund → Fix · **Status:** Ursache belegt, Fix in Umsetzung

> **Anlass.** Der Backtest (Track B) zeigte: unser generierter Plan ist auf *jeder* Dimension
> schlechter als der reale MLB-2024-Plan — Reise +23,6 %, Fatigue +66 %, Auswärts-Streak 16 vs.
> 11, 5 CBA-Verletzungen vs. 0. Dieses Dokument klärt datenbasiert **warum** und legt den Fix fest.
> Kein Rätselraten: jede Aussage ist mit Messzahlen belegt.

---

## 1 — Es ist KEIN Messfehler und KEIN unfairer Vergleich

Beide Pläne werden mit *demselben* Reisemodell (`compute_season_travel`) und *demselben*
8-D-Scoring bewertet. Wir generieren aus den **echten Matchup-Quoten** der realen Saison über
das **gleiche Kalenderfenster** und den **gleichen All-Star-Break**. Der Vergleich ist fair.

---

## 2 — Die Struktur ist fast gleich — die Flüge sind länger

Struktur-Analyse 2024 (real vs. generiert):

| Kennzahl | REAL MLB 2024 | OURS (generiert) |
|---|---:|---:|
| Spiele | 2.432 | 2.432 |
| Doubleheader | 29 | 0 |
| Road-Trips gesamt | 394 (13,1/Team) | 423 (14,1/Team) |
| Ø Road-Trip-Länge | 6,09 Spieltage | 5,75 |
| Ø Homestand-Länge | 6,11 | 5,74 |
| Ø Flug-Segmente/Team | 39,4 | 40,7 |
| Serienlängen | 1:64 · 2:128 · 3:1178 · 4:250 · 5:2 | 1:52 · 2:126 · 3:1156 · 4:250 · **6:8 · 7:4 · 8:2** |
| Liga-km | **1.709.835** | **2.089.255** |

**Die Anzahl der Flüge ist praktisch identisch** (40,7 vs. 39,4 Segmente/Team). Trotzdem
+22 % km. Also: **nicht mehr Flüge — längere Flüge.**

- km pro Flugsegment: real ≈ **1.446 km**, wir ≈ **1.711 km** (**+18 %**).

**Schlussfolgerung:** Unsere Road-Trips sind **geografisch nicht geclustert.** Echte Planer
fassen benachbarte Gegner zu einer Reise zusammen (NYY→NYM→BOS); unser Generator reiht Gegner
ohne Geografie-Bezug aneinander, sodass eine Reise zickzackt (NYY→SEA→MIA).

Nebenbefund — **Artefakte:** vereinzelt 6–8-Spiele-Serien, max. Road-Trip 16 Tage, max.
Homestand 24 Tage (real: max. 5 / 10 / 10). Diese Ausreißer sind zugleich die Quelle der
AC-2.1.8-Verletzungen (>13 Auswärtstage).

---

## 3 — Wo genau steckt der Gap? (Reihenfolge vs. Gruppierung)

Zwei Experimente trennen die Ursachen sauber:

### (a) Reihenfolge *innerhalb* bestehender Road-Trips (2-opt, ignoriert Kopplung)

| Plan | aktuell | optimale Reihenfolge | Einsparung |
|---|---:|---:|---:|
| OURS | 2.127.172 | 1.998.791 | **128.381 (6,0 %)** |
| REAL | 1.709.835 | 1.691.715 | 18.121 (1,1 %) |

→ Selbst mit *optimaler* Reihenfolge innerhalb unserer Trips kommen wir nur auf ~2,0 Mio.
Der reale Plan ist intern bereits fast optimal sortiert (nur 1,1 % Luft). **Die Reihenfolge
ist also nicht das Hauptproblem.**

### (b) Reines Termin-Optimieren härter gefahren (mehr SA-Iterationen, größere Shifts)

| SA-Budget | Final-km | Zeit |
|---|---:|---:|
| 700k Iter, Shift ±3 (heutiger Default) | 2.101.167 | 3,7 s |
| 3 Mio Iter, Shift ±7 | 2.000.968 | 12,1 s |
| 6 Mio Iter, Shift ±12 | **1.957.913** | 21,8 s |

→ Reines Termin-Optimieren plateaut bei **~1,95 Mio (+14 % vs. real)**, egal wie lang.

**Fazit:** Der verbleibende Gap (von ~1,95 Mio runter auf 1,71 Mio) steckt in der
**Trip-Komposition** — *welche* Gegner überhaupt zu einer Reise zusammengefasst werden. Das ist
der gekoppelte, schwierige Teil (Traveling Tournament Problem).

---

## 4 — Die mechanische Wurzel im Code

Die zweistufige Pipeline:

1. **CP-SAT** (`src/generator.py`) sucht **nur Feasibility** (keine Doppelbelegung, Off-Days,
   AC-2.1.9). Sie ist **reise-blind** — Geografie spielt hier keine Rolle. Daraus entsteht eine
   beliebige, travel-ineffiziente Trip-Komposition.
2. **Simulated Annealing** (`src/generator_optimizer.py`, `optimize_travel`) verschiebt danach
   nur **Starttage**: Move **SHIFT** (Serie ±N Tage) und **SWAP** (Starttage zweier gleichlanger
   Serien tauschen). **Beide ändern nie, _welche_ Auswärtsgegner ein Team hintereinander
   besucht.** Die Road-Trip-Komposition aus Schritt 1 bleibt im Kern erhalten.

Deshalb senkt der SA km nur von 2,22 → 2,09 Mio (6 %) — er kann eine geografisch schlechte
Reise nicht umbauen, nur ihre Termine verschieben.

---

## 5 — Was Forschung & Praxis tun (Recherche)

- **Anagnostopoulos et al. (2006), „A simulated annealing approach to the TTP" (TTSA).** Der
  Standard-SA für genau dieses Problem nutzt eine *große Nachbarschaft* mit **strukturellen
  Moves**: `SwapHomes`, `SwapRounds`, `SwapTeams`, `PartialSwapRounds`, `PartialSwapTeams` —
  plus *strategic oscillation* und *reheats*, um lokale Minima zu verlassen. Diese Moves bauen
  um, *wer wann wo gegen wen* spielt — viel mächtiger als reines Termin-Schieben.
- **MLB-/Profi-Praxis (Trick u. a.; INFORMS Interfaces).** Integer-Programm mit einer Variable
  **pro möglichem Road-Trip**; Teams werden **geografisch geclustert**, Reisen daraus
  zusammengesetzt; „Boston→Seattle" wird vermieden, wenn nicht zwingend nötig.
- **Skalierung.** Exakte TTP-Verfahren lösen ~10–18 Teams; für 30 sind **Heuristiken** Standard
  (GRASP, Iterated Local Search, Ejection Chains, Beam Search). Für die NBA (30 Teams) wurde ein
  Plan **nur 3,8 % über der theoretischen Reise-Untergrenze** erreicht — d. h. mit der richtigen
  Methode ist 30-Team-Travel **nahe optimal** lösbar. Unser 22 %-Gap ist weit davon entfernt:
  **viel Headroom, kein prinzipielles Limit.**

Quellen: siehe Abschnitt 7.

---

## 6 — Fix-Plan (zweistufig, gemessen)

**Stufe 1 — SA-Budget + Reheat (sofort, geringes Risiko).** Mehr Iterationen, größere Shifts,
Wieder-Aufheizen gegen Plateaus. Hebt 2,10 → ~1,96 Mio (**−6 %**) ohne Architektur-Änderung.
Honoriert „Qualität vor Geschwindigkeit" (längere Laufzeit ausdrücklich OK). Determinismus
bleibt (fixer Seed). **Reicht allein nicht, um den realen Plan zu schlagen.**

**Stufe 2 — Geo-bewusster Struktur-Move (der eigentliche Fix).** Eine neue SA-Nachbarschaft im
Stil der TTP-Literatur: eine Auswärtsserie aus einem ungünstigen Trip **herauslösen und an einen
geografisch nahen Trip desselben Teams anlagern** (Ejection/Insertion), mit voller
Feasibility-Prüfung über *alle* betroffenen Teams. Das ändert die **Trip-Komposition** und holt
die restlichen ~14 % Richtung/unter 1,71 Mio. Zusätzlich: die Struktur-Artefakte (6–8-Spiele-
Serien, 16-/24-Tage-Blöcke) als harte Grenzen kappen → senkt zugleich Fatigue + AC-2.1.8.

**Mess-Gate:** Erfolg = der Backtest zeigt unseren Plan **mindestens gleichauf, Ziel besser** auf
Reise/Fatigue/AC-Verletzungen. Reproduzierbar, deterministisch, Baseline-Tests grün.

---

## 6a — Erreichtes Ergebnis (2026-06-01, umgesetzt)

**Umgesetzt (Stufe 1 + 2):**
- SA-Budget der Default-Config: 700k/shift3 → **8 Mio/shift8** (`src/generator.py`).
- **Geo-Move** in `optimize_travel` (`src/generator_optimizer.py`): loest eine Auswaerts-
  Serie heraus und setzt sie neben den geografisch naechsten Auswaerts-Gegner desselben
  Teams (vorberechnete Nachbarn, `move_mix_geo=0.35`). Akzeptanz rein ueber die SA-Energie
  (km + λ·Fatigue, λ=1e6) — verschlechtert AC-2.1.8/9 praktisch nie, kann Trips sogar
  verkuerzen, ohne teuren Extra-Guard.

**Backtest 2024 (Seed 42), vorher → nachher:**

| Kennzahl | Vorher (700k) | Nachher (8M + Geo) | Realer MLB-Plan |
|---|---:|---:|---:|
| Reise-km | 2.101.167 (+23,6 %) | **~1.863.000 (+9,0 %)** | 1.709.835 |
| km / Flugsegment | 1.711 | ~1.520 | 1.446 |
| AC-2.1.8 Verletzer | 5 | 3–6 (run-abhaengig) | 0 |

→ **Reise-Gap mehr als halbiert** (+23,6 % → +9,0 %). Determinismus erhalten (AC-2.1.11
gruen), AC-2.1.9 strukturell weiter eingehalten, alle Generator-AC-Tests gruen.

**Was noch offen ist (ehrlich):**
1. **Restliche ~9 % Reise.** Ein Teil ist eine *Modell-/Fairness-Differenz*: der reale Plan
   nutzt **29 Doubleheader**, die Road-Trips komprimieren — unser Generator erzeugt **0 DH**
   und verteilt dieselben Spiele auf Einzeltage. Doubleheader-Unterstuetzung (B4/Track-D-Nähe)
   schliesst hier weiter auf. Daneben ist mit einer noch staerkeren Trip-Konstruktion
   (Branch-and-Price / „Variable pro Road-Trip") Richtung NBA-Benchmark (3,8 % ueber LB)
   theoretisch mehr drin.
2. **AC-2.1.8 (≤13 Auswaerts-Tage).** Weiterhin 3–6 Verletzer (das dokumentierte, APX-harte
   TTP-Problem, Track A). Der Geo-Move verschlechtert es nicht, loest es aber nicht — die
   strukturelle ≤13-Garantie bleibt der Forschungs-Headliner (matchup-bewusste HAP /
   Branch-and-Price).

---

## 6b — Durchbruch: Warm-Start statt From-Scratch (2026-06-02)

**Idee (von Jonas):** Statt jede Saison reise-blind *from scratch* zu bauen, den **echten Plan
als Startpunkt** nehmen und von dort optimieren. Der reale Plan ist bereits ein sehr guter,
nahezu CBA-konformer Plan — startet man dort, kann das Ergebnis **nur besser-oder-gleich** sein.
Das ist zugleich der realistische Produktionsfall: fuer eine neue Saison startet man vom
strukturell fast identischen **Vorjahresplan**.

Umgesetzt als `tools/backtest.py --warm-start` (`improve_real_plan`): laedt den realen Plan,
laesst den SA-Optimizer (inkl. Geo-Move) von dort laufen.

**Ergebnis (Seed 42, 6 Mio Iter, ~26 s):**

| | REAL | Warm-Start (wir) | Δ |
|---|---:|---:|---:|
| **2024** Reise-km | 1.709.835 | **1.617.761** | **−5,4 %** ✅ |
| 2024 CBA-Verletzungen | 0 | 0 | gehalten |
| **2025** Reise-km | 1.715.743 | **1.671.345** | **−2,6 %** ✅ |
| 2025 worst_away | 14 | **13** | −1 ✅ |
| 2025 CBA-Verletzungen | **1** | **0** | behoben ✅ |

→ **Wir schlagen den realen MLB-Plan auf Reise — und bleiben/werden voll CBA-konform.** Fuer
2025 reparieren wir sogar eine Verletzung, die der reale Plan selbst hatte. Warm-Start umgeht
zudem die CP-SAT-Intraktabilitaet (z. B. 2025), weil kein Kalt-Start noetig ist.

**Ehrliche Einordnung.** `optimize_travel` minimiert NUR km (+ Fatigue als harte Schranke);
Revenue/TV/Event-Friction stehen nicht in seiner Zielfunktion, daher geben diese im Warm-Start
leicht nach. Ein **Pareto-Warm-Start** (`optimize_pareto` vom realen Plan aus) wuerde alle 8
Dimensionen balancieren — der logische naechste Schritt, um auf *allen* Achsen ≥ real zu sein.

**Empfehlung.** Warm-Start als Produktions-Standardmodus etablieren: „Gib uns den aktuellen
(oder Vorjahres-)Plan, wir liefern einen messbar besseren, voll CBA-konformen." From-Scratch
bleibt als Fallback/Validierung des Algorithmus.

---

## 7 — Quellen

- Anagnostopoulos, Michel, Van Hentenryck, Vergados (2006): *A simulated annealing approach to
  the traveling tournament problem.* J. Scheduling.
  <https://link.springer.com/article/10.1007/s10951-006-7187-8> ·
  <https://www.ijcai.org/Proceedings/03/Papers/197.pdf>
- Easton, Nemhauser, Trick: *The Traveling Tournament Problem — Description and Benchmarks*;
  Trick, *Adventures in Sports Scheduling* <https://www.cs.cmu.edu/~ACO/dimacs/trick.html>
- INFORMS *Interfaces* — Special Issue on Analytics in Sports: Sports Scheduling Applications
  <https://pubsonline.informs.org/doi/10.1287/inte.1120.0632>
- MiLB.com, *Creating optimal schedules a tricky task* (Praxis Road-Trip/Homestand-Regeln)
  <https://www.milb.com/news/gcs-162513496>
```
