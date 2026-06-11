# Sprint 5.4 + 5.5 — Green-field (Gurobi/B3) & Chronobiologie (D1–D3)

**Stand:** 2026-06-10. 5.4 liefert den green-field Solver inkl. vollständigem Gurobi-
Lizenz-Plumbing („nur Key reinpasten"); 5.5 die konservativen, fairen Chronobiologie-
Gewichte. 5.4-Voll-Saison bleibt lizenz-/forschungs-gegatet (TTP-Härte).

---

## 5.4 — Green-field Schedule from scratch (FORK 2)

### B3 — Balanced-Schedule-Format (`src/balanced_schedule.py`)
MLB-2023+-Format als strukturelle Constraints: 162 Spiele/Team = 52 Intra-Division
(13×4) + 64 Intra-League (6/7 ×10) + 46 Interleague (3/4 ×15). Funktionen:
`category`, `derive_matchup_matrix` (aus Referenzsaison), `canonicalize_matrix`
(Makeup-Artefakte → kanonisch), `validate_format` (B3-Compliance), `round_robin_matrix`
(reduzierte Instanzen), `format_summary`.

**Messung:** real **2024 = 0 Format-Verstöße** (sauberes Balanced-Format); 2025 = 2
(as-played-Interleague-Streuung + CIN 165 = Makeups). Canonicalize stellt Team-Totals
auf 162 ±1 her.

### Green-field Gurobi-Solver (`src/greenfield_gurobi.py`)
TTP-MIP: `h[i,j,d]` (i hostet j an Tag d) + `p[i,c,d]` (Stadt-Persistenz) mit linearer
Reise-Linearisierung (McCormick). Constraints: Matchup-Quoten (B3), ≤1 Spiel/Team/Tag,
Stadt-Konsistenz, ≤max_consecutive (V(C)(12)). Ziel: **reale Reise-km** minimieren.

**Lizenz-Plumbing („nur Key reinpasten"):** `gurobi_status()` + `_make_env()` lesen die
Lizenz automatisch aus `.env` (`src/config.get_gurobi_wls()`):
`GRB_WLSACCESSID`/`GRB_WLSSECRET`/`GRB_LICENSEID` (akademisches WLS) **oder**
`GRB_LICENSE_FILE` (gurobi.lic). Platzhalter stehen in `.env`. **Ohne Lizenz**:
Restricted License (größenlimitiert) löst **kleine Instanzen sofort** (verifiziert:
3 Teams, 2 Spiele/Paar, 9 Tage → **OPTIMAL in 0,3 s**, korrekte Matchup-Quoten, ≤1
Spiel/Team/Tag). Größere Instanzen → klare `GurobiUnavailable`-Meldung „Model too large
for size-limited license" mit Hinweis auf die `.env`-Lizenz. **Demo:**
`python -m tools.greenfield_demo --teams NYY,BOS,TBR --games-per-pair 2 --days 9`.

**Ehrliche Einordnung (TTP-Härte):** Das direkte MIP löst reduzierte Instanzen optimal;
die volle 30-Team-Saison ist TTP-hart (APX-hart, vgl. Q10). Jonas' akademische Lizenz
hebt das **Größenlimit**; der **Tractability-Pfad** für 30 Teams ist die Spalten-
Generierung / Branch-and-Price (Dekomposition; HAP-Gerüst in `src/colgen`). Damit ist der
green-field Kern korrekt + getestet und das Lizenz-Plumbing vollständig — Jonas trägt nur
die drei WLS-Werte ein.

### Branch-and-Price / Column Generation (`src/branch_and_price.py`)
Skalierungs-Pfad für die volle Saison (Dantzig-Wolfe **nach Team**):
- **Spalte** = feasibler Einzel-Team-Spielplan (welche Spiele an welchem Tag) mit eigener
  Reise-km.
- **Restricted Master (Gurobi)** = Set-Partition: eine Spalte je Team (LP-konvex/integer)
  + **Game-Consistency-Coupling** (h hostet v an Tag d ⟺ v ist auswärts bei h an Tag d).
- **Pricing-Subproblem** je Team (Gurobi) mit den RMP-Dualwerten → neue Spalte mit
  negativen reduzierten Kosten.
- **Price-and-Branch:** Spalten generieren (LP), dann integer RMP über den Pool. **Bootstrap
  (greedy, immer feasibel)** garantiert, dass die Engine **nie schlechter** als der Startwert
  wird; `seed_schedules=` nimmt hochwertige Pläne (SA/monolithisch) als konsistente Spalten auf.

**Validierung (reduziert, 3 Teams):** gültiger, matchup-kompletter, konsistenter Plan;
mit Seed des monolithischen Optimums **erreicht der integer Master genau dieses Optimum**
(11.623,6 km) und schlägt den greedy Bootstrap (11.641,6) — Master + Coupling sind also
korrekt. **Demo:** `python -m tools.greenfield_demo --method bnp --teams NYY,BOS,TBR …`.

**WICHTIGER Korrektur-Befund:** Beim B&P-Bau fiel auf, dass der **monolithische** Solver
die Reise **unter-zählte** (kein Off-Day-Persistenz-Constraint → „Teleport" gratis an
Off-Days, keine Heim-Anker-Legs). **Gefixt:** `solve_greenfield` hat jetzt Off-Day-
Persistenz + Heim-Anker → **echte** Reise-km (monolithisch == decomposed _column_cost,
bit-genau). Damit messen beide Solver dieselbe Wahrheit.

**Ehrlich:** Reines (ungeseedetes) Column-Generation verbessert auf eng gekoppelten
Kleinst-Instanzen kaum über den Bootstrap — unabhängiges Pricing koordiniert die global
konsistenten Spalten-Sets nicht (das ist die TTP-B&P-Forschungsfront; nächster Schritt =
echtes Branching im B&P-Baum oder runden-basierte Dekomposition). Die Engine ist die
**korrekte, getestete Infrastruktur** + ein praktischer Price-and-Branch-Modus, der mit
Seeds das Optimum erreicht und mit Jonas' Key auf größere Instanzen skaliert.

### Echtes Branch-and-Price-Branching (`branch_and_price_optimal`)
DFS-Baum mit **Event-Branching** (host hostet visitor an Tag d): fraktionales x_e →
Kind A erzwingt e, Kind B verbietet e; das Pricing respektiert die Entscheidung
(forced/forbidden als Constraints), Bounding via LP-Schranke, Knoten-/Zeitlimit.
Validiert: gültig, nie schlechter als Bootstrap, erreicht mit Seed das Optimum.

**Ehrliches, präzises Forschungs-Ergebnis (wichtig):** Reines per-Team-Pricing
**kann den Bootstrap nicht verbessern**, und zwar strukturell, nicht durch einen Bug:
Spalten aus verschiedenen (je intern konsistenten) Plänen sind **untereinander
inkonsistent** (Team A's Spalte aus Plan 1 passt nicht zu Team B's Spalte aus Plan 2 auf
den Spieltagen). Konsistente *verbessernde* Spalten-Sets müssen **gemeinsam** erzeugt
werden — unabhängiges Pricing leistet das nicht (zusätzlich verschärft durch
Dual-Degeneration bei 1 Spalte/Team). Das ist exakt der bekannte Grund, warum TTP-B&P
**nicht** per-Team, sondern über **Trip-/Pattern-Spalten** oder **runden-basiert**
dekomponiert wird. Die Engine ist die korrekte Infrastruktur + Validierung dieses Befunds.

### Runden-/Fenster-Dekomposition (`src/greenfield_decomp.py`) — der praktische Skalierer
Rolling-Horizon: der Horizont wird in **Zeitfenster** zerlegt; jedes Fenster re-optimiert
seine Spiele **team-gekoppelt** mit Gurobi (inkl. Reise-Kontinuität: Eintritts-Stadt =
Endstadt des Vorfensters), Sweep über mehrere Pässe. Im Gegensatz zur per-Team-Dekomposition
löst jedes Fenster ein gekoppeltes Sub-MIP → erzeugt konsistente Verbesserungen.
**Garantie:** ein Fenster-Update wird nur übernommen, wenn die globale Reise **nicht
steigt** → Ergebnis **≤ Bootstrap** (monoton).

**Validierung:** gültiger, matchup-kompletter Plan; **skaliert auf 4 Teams, wo der
monolithische Solver das Restricted-Größenlimit sprengt** — Fenster-Dekomposition liefert
dort 14.186,7 km (Bootstrap 14.537,9 → −2,4 %) in 0,45 s. Deterministisch.
**Demo:** `python -m tools.greenfield_demo --method windowed --teams LAD,SDP,SFG,SEA …`.

### Trip-/Pattern-basierte Formulierung — runden-indiziert (`src/ttp_rounds.py`)
Der exakte nächste Schritt nach der per-Team-Dekomposition: **runden-indiziert** statt
tag-indiziert. Jede Mannschaft spielt **genau 1× pro Runde** (klassische TTP-Struktur;
eine Runde = perfektes Matching). Die H/A-Folge eines Teams über die Runden **ist** sein
Home-Away-Pattern (HAP); das Modell wählt simultan Pattern + Gegner + Reise, mit direktem
**Roadtrip-Längen-Constraint** (≤ konsekutive Auswärtsrunden = strukturelles
AC-2.1.8-Analogon). **Entscheidend kompakter:** Rundenzahl R = gpp·(n−1) ≪ Kalendertage
→ löst Instanzen, an denen das tag-indizierte MIP am Größenlimit scheitert.

**Validierung:** **n=4 → OPTIMAL (gap 0) in 0,12 s** — genau dort, wo das tag-indizierte
monolithische MIP unter der Restricted License das Größenlimit sprengt. Ergebnis
14.186,7 km = identisch zum Fenster-Heuristik-Ergebnis → **kreuz-validiert dessen
Optimalität**. Perfektes Matching je Runde, matchup-komplett, Roadtrip-Limit eingehalten,
deterministisch. n≥6 braucht die akademische Lizenz (Größenlimit). `rounds_to_days()`
bildet auf Kalendertage ab (Off-Day-Abstand). **Demo:**
`python -m tools.greenfield_demo --method rounds --teams LAD,SDP,SFG,SEA --games-per-pair 2`.

**Einordnung:** Das ist die richtige TTP-Dekomposition — runden-/pattern-basiert, NICHT
per-Team. Sie löst exakt und kompakt; mit Jonas' Key skaliert sie auf mehr Teams. Die
Fenster-Dekomposition bleibt der heuristische Skalierer für sehr lange Horizonte; beide
Resultate stimmen auf n=4 überein (Optimalitäts-Beleg).

### Status nach Key-Eintrag
1. `.env`: `GRB_WLSACCESSID/SECRET/LICENSEID` ausfüllen.
2. `python -m tools.greenfield_demo --teams … --method monolithic|bnp|windowed|rounds`.
3. **Empfohlener Voll-Saison-Pfad:** **runden-/pattern-basiertes MIP** (`ttp_rounds`,
   exakt, kompakt) als Kern, für sehr große Horizonte die Fenster-Dekomposition
   (≤-Bootstrap-Garantie); danach optional SA-Travel-Politur. Per-Team-B&P bleibt
   Infrastruktur/Lehrstück (strukturell limitiert, s. o.).

---

## 5.5 — Chronobiologie / Jet-Lag (D1–D3) (`src/chronobiology.py`)

**D1 Evidenz + Diskontierung:** Song/Severini/Allada (2017, *PNAS*) — Ostwärts-Reisen
beeinträchtigen MLB-Leistung stärker als Westwärts, Effekt skaliert mit Zeitzonen, klingt
~1 TZ/Tag ab (Eastman/Burgess 2009); Recht et al. (1995, *Nature*). **Konservativ
diskontiert** (`DISCOUNT=0.25`) wegen moderner Charter/Ruheregeln/Recovery → der Index ist
ein **relativer Belastungsindex**, keine Leistungsprognose.

**D2 Mapping-Transparenz:** dimensionsloser Index = Tagesintegral der zirkadianen „Schuld"
(Ostwärts-Gewicht 1.0 > Westwärts 0.6 je TZ; Erholung 1 TZ/Tag; × DISCOUNT). Mapping
offengelegt + **sensitivitätstestbar** (Tests: discount skaliert linear, höheres
Ost-Gewicht erhöht Belastung monoton).

**D3 Fairness/Symmetrie:** **identische Gewichte für alle Teams**, dasselbe Modell — kein
struktureller Vorteil. Der Index misst nur die **plan-bedingte** Belastung. Fairness-
Kennzahl = Gini.

**Gating:** reine Analyse-/Reporting-Schicht, **kein** Eingriff in den deterministischen
Optimierpfad (Default-Pfad bit-identisch).

**Messung (real):** 2024 total ≈ 422 (Gini 0,19), 2025 ≈ 433 (Gini 0,19). Höchste
Belastung erwartungsgemäß West-Teams (OAK, ARI, LAD, SDP, SFG, LAA — viel Ostreise),
niedrigste Central/Ost (CHC, TBR, NYY) — richtungs-sensitiv und plan-bedingt, nicht
modell-unfair.

**Tests:** `tests/test_sprint_5_5_chronobiology.py` (9): kein-TZ-Reise=0, Ostwärts>Westwärts,
Sensitivität (linear/monoton), Fairness (identische Gewichte, Gini<0,5), Richtungs-Sanity
(West>Central), Determinismus.

---

## Akzeptanz
5.4: B3 implementiert + real validiert; green-field Solver korrekt + getestet (reduziert
optimal); Lizenz-Plumbing vollständig „paste-key". 5.5: D1–D3 evidenzbasiert, konservativ
diskontiert, fair/symmetrisch, Mapping offengelegt + sensitivitäts-/fairness-getestet.
