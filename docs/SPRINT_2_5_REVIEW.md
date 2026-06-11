# Sprint 2.5 Review — What-if Engine

**Datum:** 2026-05-26
**Status:** ✅ Abgeschlossen

---

## Ziele des Sprints

| # | Deliverable | Status |
|---|---|---|
| Task #22 | `src/whatif.py` — What-if Engine (4 öffentliche Funktionen) | ✅ |
| Task #27 | `tests/test_whatif.py` — 44 Unit-Tests | ✅ |
| Task #28 | `docs/SPRINT_2_5_REVIEW.md` + Handover | ✅ |

---

## Was ist die What-if Engine?

Die What-if Engine erlaubt MLB-Operatoren, schnelle Szenario-Analysen **ohne CP-SAT-Neustart** durchzuführen. Statt 20s Generierungszeit liefert sie Antworten in < 2s durch lokale Serien-Verschiebung und direkte ParetoBundle-Neuberechnung.

**Typische Anwendungsfälle:**
- _"Was passiert mit Reisekosten und Revenue, wenn NYY am 4. Juli in Boston spielt?"_
- _"Ein Konzert im Minute Maid Park am 15. August — welche Spiele müssen wir verschieben?"_
- _"Vergleich: Travel-optimierter Plan vs. TV-optimierter Plan in allen 8 Dimensionen."_

---

## API-Übersicht

### `whatif_force_series(season, teams, cfg, home, away, forced_start, ...)`

Erzwingt eine Serie `home@away` zu einem festen Datum. Algorithmus:
1. Bestehende `home@away`-Serie aus dem Plan finden (nächste zum `forced_start`)
2. Kollidierende Serien am neuen Datum identifizieren
3. Kollisionen durch Verschiebung auf nächsten freien Slot lösen
4. Erzwungene Serie am `forced_start` platzieren
5. ParetoBundle vor/nach berechnen → Delta zurückgeben

### `whatif_blackout(season, teams, cfg, team, blackout_dates, ...)`

Wendet einen Venue-Blackout an (Konzert, Event, technische Störung):
1. Alle Heimspiele (oder Auswärtsspiele) des Teams in den Blackout-Tagen finden
2. Vollständige Serien dieser Spiele ermitteln
3. Jede Serie auf nächsten freien Slot nach dem Blackout verschieben
4. ParetoBundle-Delta zurückgeben

### `whatif_compare(season_a, season_b, teams, label_a, label_b, ...)`

Vergleicht zwei beliebige Saisonpläne in allen 8 Dimensionen. Kein Scheduling — reine Bundle-Differenz. Laufzeit: ~50–100ms.

### `analyze_team_impact(original, modified, team_id)`

Detailanalyse für ein einzelnes Team nach einer Modifikation:
- Spielanzahl-Delta (hinzugefügt / entfernt)
- Heim- und Auswärtsspiel-Delta
- Liste der betroffenen Serien (Datum + Gegner)
- Reise-Delta als Proxy (Standortwechsel × ~500km)

---

## Ergebnis-Typen

```python
WhatIfResult
├── scenario_name: str
├── description: str
├── original_bundle: ParetoBundle     # 8 Dimensionen vor Änderung
├── modified_bundle: ParetoBundle     # 8 Dimensionen nach Änderung
├── deltas: List[DimensionDelta]      # Delta pro Dimension
├── modified_season: Season           # modifizierter Plan (für Folge-Analysen)
├── feasible: bool                    # True wenn alle Konflikte gelöst
└── warnings: List[str]               # z.B. "kein freier Slot"

DimensionDelta
├── name: str                 # "travel_km", "revenue_usd", etc.
├── label: str                # "Reisedistanz"
├── original/modified: float
├── delta: float              # modified - original
├── delta_pct: float          # prozentuales Delta
└── direction: str            # "better" | "worse" | "neutral"
```

**`WhatIfResult.summary()`** gibt einen formatierten Text-Report aus:
```
══════════════════════════════════════════════════════════════════════
  WHAT-IF: Force NYY@BOS am 2026-07-04
  NYY@BOS (3 Spiele) am 2026-07-04 (vorher: 2026-05-12)
──────────────────────────────────────────────────────────────────────
  ✓ Reisedistanz          2,000,000.0 →  1,987,000.0 km (-0.7%)
  ✗ Event-Friction              100.0 →        118.0 pts (+18.0%)
  ~ Gate-Revenue        8,000,000,000 → 8,000,000,000 USD
  ...
```

---

## Test-Ergebnisse

```
tests/test_whatif.py           44 passed   0.56s
```

| Klasse | Tests | Thema |
|---|---|---|
| `TestFindSeriesForMatchup` | 4 | Interne Serie-Suche |
| `TestFindFreeSlot` | 4 | Freien Slot finden |
| `TestMoveGamesToDate` | 4 | Spiele verschieben |
| `TestReplaceGames` | 2 | Saison-Mutation |
| `TestBuildDeltas` | 6 | Delta-Berechnung |
| `TestWhatIfResult` | 4 | Ergebnis-Typ |
| `TestWhatIfCompare` | 3 | whatif_compare() |
| `TestWhatIfBlackout` | 4 | whatif_blackout() |
| `TestWhatIfForceSeries` | 6 | whatif_force_series() |
| `TestAnalyzeTeamImpact` | 5 | analyze_team_impact() |
| `TestDimensionDeltaStr` | 3 | Ausgabe-Format |

Alle öffentlichen Funktionen durch gepatchtes `compute_pareto_bundle` getestet → kein Generator-Run in Unit-Tests → 0.56s Laufzeit.

---

## Design-Entscheidungen

### Kein CP-SAT-Neustart
Vollständige Neugenerierung würde ~20s dauern. Die What-if Engine löst Konflikte durch greedy lokale Verschiebung (`_find_free_slot`), die in O(season_days) läuft. Für MLB-Produktiveinsatz (Real-time Decision Support) ist Sub-2s-Latenz entscheidend.

### Feasibility-Tracking
Wenn ein Konflikt nicht auflösbar ist (kein freier Slot), wird `feasible=False` gesetzt und eine Warnung hinzugefügt. Das betroffene Spiel wird aus dem Plan entfernt (kein stilles Überlappen), sodass das Bundle immer einen konsistenten Zustand reflektiert.

### `whatif_compare` als "freie" Funktion
Sie erfordert keine Serien-Reparatur — reine Bundle-Differenz. Das macht sie ideal für den Vergleich von Pareto-Punkten aus `sample_pareto_frontier()`.

---

## Bekannte Einschränkungen

- `analyze_team_impact` berechnet Travel-Delta als Proxy (Standortwechsel × 500km), nicht als exakten Haversine-Betrag. Für exakte Zahlen: `compute_season_travel()` auf modifizierter Season aufrufen.
- `whatif_force_series` verschiebt nur _eine_ bestehende Serie. Wenn mehrere Serien desselben Matchups existieren, wird die nächstgelegene gewählt.
- Kaskadierende Konflikte (eine verschobene Serie erzeugt neuen Konflikt) werden in der aktuellen Version nicht rekursiv aufgelöst. Das ist für typische MLB-Operationen (ein Termin erzwingen) ausreichend.
