# Sprint 3 — P0 + P1-3/P1-4 Review (2026-06-07)

**Umgesetzt:** P0 (Produktionspfad festgeschrieben) sowie P1-3 (Getaway-Day-
Feasibility + Feiertags-Pins) und P1-4 (Compliance + Explain) — genau Schritt 1+2
der empfohlenen Reihenfolge aus `docs/PROJECT_REVIEW_2026-06.md`.

---

## P0 — Warm-Start ist der einzige Produktionspfad

- **Entscheidung dokumentiert:** `docs/DECISION_P0_PRODUCTION_PATH.md` (mit
  Kennzahlen, Begründung, Langfrist-Item Branch-and-Price).
- **Code:** `src/main.py` — Warm-Start ist jetzt **Default**. From-Scratch nur
  über `--from-scratch` (mit Warnhinweis, „nur Algorithmus-Validierung").
  `--warm-start` bleibt als No-Op (Rückwärtskompatibilität).
- **Doku:** `README.md` + `docs/ARCHITECTURE_DECISION.md` aktualisiert.
- AC-2.1.8-`xfail` im From-Scratch-Pfad ist damit **bewusst** und kein offener
  Produktions-Blocker mehr.

## P1-3 — Reise-Feasibility + Feiertags-Pins

### `src/feasibility.py` (Getaway-Day-Feasibility)
Flaggt unrealistische Back-to-Backs (Intercity ohne Off-Day). **Datenbasierte
Schwellen** aus real 2024+2025 gemessen:
- längster realer konsekutiver Transfer = **4164 km / 3 TZ-Hops** → Envelope-
  Ceiling 4200 km / 3 Hops.
- 3 Team-Paare (SEA-MIA, BOS-SFG, BOS-OAK) liegen über 4200 km und werden von
  MLB **nie** als Back-to-Back gelegt → genau die fängt der `exceeds_real_envelope`-
  Check.
- Klassifikation: `ok` / `tight` (ostwärts, ≥2 Hops, ≥ p95 km — Review-Hinweis) /
  `exceeds_real_envelope` (echter Verstoß).
- **Reale Pläne bestehen sauber** (0 Verstöße) — Envelope korrekt kalibriert.
- Bewusst distanz-/TZ-basiert (nicht day/night): unser Plan-Output ist auf
  Tagesebene ohne Anstoßzeiten; day/night wäre wirkungslos. Day/night-Layer ist
  als optionale Erweiterung vorgesehen (Uhrzeiten-Zuweisung als Vorarbeit).

### `data/holiday_pins.json` + `src/holidays.py` (Feiertags-Pins)
Opening Day, Jackie Robinson Day (15.4.), Memorial Day, 4. Juli, Labor Day als
Pins/Incentives. `league_wide` = voller Slate (alle 30 Teams aktiv);
`marquee_incentive` = Marquee-Matchups (aus `data/tv_slots.json`, nicht
dupliziert). Deterministische Datumsberechnung (fix / nth-weekday / opening_day).
Reporting+Scoring, verändert keinen Plan.

## P1-4 — Verteidigbarkeit

### `src/compliance.py` (Compliance-Report)
Jede Hard-Rule ↔ Quelle (CBA-Artikel / MLB-Regel / Doc) mit Messwert +
Pass/Fail + **maschinenlesbarem Provenance-Register** (`to_dict`/`to_json`).
Regeln: AC-2.1.8, AC-2.1.9, SCHED-162 (Vollständigkeit, referenz-/toleranzbasiert),
SCHED-HA, FEAS-GETA, PIN-LEAGUE (soft). **Realer 2024-Plan = voll compliant**
(alle harten Regeln bestehen).
- **Kalibrierungs-Befund (ehrlich):** gespielte Saisonen streuen real 161–163
  Spiele/Team (Makeups/Ties/DH). Eine starre „genau 162"-Regel hätte den realen
  Gold-Standard-Plan fälschlich als non-compliant geflaggt → Count-Checks sind
  toleranz-/referenzbasiert (mit Referenz-Counts: exakte Prüfung, fängt
  verlorene/duplizierte Spiele wie den früheren DH-Roundtrip-Bug).

### `src/explain.py` (menschenlesbare Begründung)
Deutschsprachige Markdown-Begründung: Überblick, Reise (+Δ vs. Baseline),
Regel-Compliance, Reise-Feasibility, härteste Road-Trips, Feiertags-Highlights.
Faktenbasiert, jede Aussage messbar.

## Tests & Verifikation

- **Neu:** `tests/test_sprint_3_compliance.py` — **20 Tests, alle grün**
  (feasibility, holidays, compliance, explain; inkl. Determinismus, Provenance,
  reale Plan-Integration).
- **Keine Regression:** alle relevanten bestehenden Nicht-Slow-Suites grün
  geprüft (fatigue, invariants, sprint_2_3b Pareto-Determinismus, backtest,
  phases, sustainability, whatif(_demo), tv_revenue, disruption/repair, q10).
- Neue Module sind rein additiv; einzige Änderung an Bestandscode = `src/main.py`
  (von keinem Test importiert) + Docs.
- **Bekannt (nicht neu, umgebungsbedingt):** `test_sprint_2_3a` HAP/PhaseB-
  CP-SAT-Tests timen in der Sandbox aus (Solver 30,2s > 30s-Assertion,
  1-Worker). Unabhängig von dieser Arbeit (kein Import der neuen Module);
  CI-Umgebung mit mehr Ressourcen erforderlich.

## Nachtrag (gleiche Session): SA-Soft-Terme + P1-2 Doubleheader

### Feasibility + Feiertage als weiche SA-Terme (P1-3, planungswirksam)
Beide Reporting-Module wirken jetzt **aktiv im Produktionspfad** (`optimize_travel`,
den `main.py --warm-start` nutzt). Energie = `km + λ_fat·fatigue + λ_feas·feasibility
+ λ_hol·holiday`.
- **Feasibility-Penalty** (per-Team, inkrementell wie die Fatigue-Penalty):
  `exceeds_real_envelope` hart, `tight` leicht bestraft. `feas_lambda` Default 0.0.
- **Feiertags-Incentive** (global, Belegungszähler auf den wenigen Feiertagstagen):
  fehlende Slate-Abdeckung (league_wide) + fehlende Marquee-Spiele. `holiday_lambda`
  Default 0.0.
- **Determinismus:** beide hinter λ-Gate; bei λ=0 ist `_energy` bit-identisch zur
  alten Formel (`x + 0.0 == x`). Verifiziert: Warm-Start-Determinismus-Tests grün,
  Pareto-Determinismus (68 Tests) grün.
- **Gemessene Wirkung (real 2024, messen statt behaupten):** Die reine km-SA
  *erzeugt* selbst 1 Envelope-Verstoß + 16 harte Turnarounds; mit `feas_lambda=50k`
  → zurück auf 0/2 (wie real). Der Holiday-Term hebt Memorial Day 20→24 und Labor
  Day 22→26 Teams aktiv — **über** dem realen Plan — während km-only sie auf 18/22
  verschlechtert.

### P1-2 Doubleheader-Planung (`src/doubleheaders.py`)
Day-Night-DH als Verdichtungswerkzeug. Kern: **Tail-Compression** — die letzten
zwei Spieltage einer Serie fallen zu einem DH am vorletzten Tag zusammen, Serie −1
Tag. **Matchup-erhaltend** (Spielanzahl exakt), **occupancy-schrumpfend** (kein
neuer Overlap, Break-Days/Blackouts bleiben respektiert). `plan_doubleheaders_for_
fatigue` verdichtet die letzte Auswärtsserie zu langer Road-Trips → Spanne −1 je DH,
bis ≤ Limit. Opt-in in `optimize_travel` via `enable_dh_compression` (Default aus).
Verifiziert: 14-Tage-Trip → 13, 14 Spiele erhalten, echter Day-Night-DH (seq 1/2).
Grenze v1: greift nur, wenn die letzte Trip-Serie ≥2 Tage hat (sonst no-op, dokumentiert).

### CLI
`main.py` (Warm-Start) hat jetzt `--feas-lambda`, `--holiday-lambda`,
`--dh-compression` (alle Default aus → unverändertes Verhalten).

### Tests
`tests/test_sprint_3_sa_terms.py` — **11 Tests grün** (Feasibility-Helfer,
Determinismus all-off/feas-on/holiday-on, Wirkung, DH-Verdichtung + Integration).
Gesamt-Regression der determinismus-/generator-kritischen Suites grün.

## Nachtrag (gleiche Session): P1-5 — Geo-Move + Terme in `optimize_pareto`

Der multi-objektive Pfad (`optimize_pareto`) ist jetzt so stark wie der
Reise-Pfad: **Geo-Move** (Ejection/Insertion neben den nächsten Auswärtsgegner)
sowie die **Feasibility-** und **Holiday-Terme** sind 1:1 gespiegelt.
- **Move-Dispatch:** ein `rng.random()` entscheidet GEO/SHIFT/SWAP. Bei
  `move_mix_geo=0` ist `shift_cut == move_mix_shift` → **exakt dieselbe
  rng-Sequenz und Verzweigung** wie zuvor.
- **Feasibility + Holiday** sind vollständig in `_apply_shift_update`/
  `_revert_shift` gekapselt (decken damit GEO/SHIFT/SWAP gemeinsam ab); Energie
  `+ FEAS_LAMBDA·feas + HOLIDAY_LAMBDA·holiday`.
- **Determinismus:** alle drei hinter Gate (Default 0) → bit-identisch. Verifiziert:
  **alle 68 Pareto-Unit-Tests + 18 Slow-Front-Tests grün** (unverändert), plus 4
  neue P1-5-Tests (Determinismus all-off/geo/feas/holiday + Geo verbessert km).
- **Gemessene Wirkung (real 2024, balanced, 1500 Iter):** Geo-Move senkt die
  Pareto-Reise 1.709.835 → 1.698.181 km; der Feasibility-Term verschlechtert die
  Verstöße nie.
- **Durchgereicht:** `pareto.sample_pareto_frontier(sa_move_mix_geo/sa_feas_lambda/
  sa_holiday_lambda)` und `main.py --pareto-geo` (nutzt zusätzlich `--feas-lambda/
  --holiday-lambda`).

## Offen / Nächste Schritte

- **TTP-Nachbarschaften** (Ejection Chains / 2-opt über Trips) über den Geo-Move
  hinaus, falls noch mehr Reise-Hebel im Pareto-Pfad gewünscht.
- Feasibility: optionaler day/night-Layer, sobald Anstoßzeiten zugewiesen werden.
- DH-Compression v2: Compression + Pull-in der Folgeserien (greift auch, wenn die
  letzte Trip-Serie nur 1 Spiel hat); DH-Makeup-Logik im Disruption-Handler.
- HAP/PhaseB-Tests als `@pytest.mark.slow` markieren (Sandbox-Tractability).
- Empirisch das beste λ_feas/λ_holiday auf vollen 6M-Iterationen kalibrieren
  (hier auf 5k–40k Iterationen gemessen).
