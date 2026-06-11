# Saison-Phasen — der Scheduler steuert Prioritäten pro Zeitfenster

**Stand:** 2026-06-02 · **Modul:** `src/phases.py` · **Integration:** `optimize_pareto(..., phase_plan=...)`

## Wozu

Der Kern dessen, was MLB Season Schedulers den Planungs-Job abnimmt: Nicht eine
einzige Gewichtung über die ganze Saison, sondern **Prioritäten pro Phase**. Der
Scheduler sagt der Maschine, *wann* *was* zählt — die Maschine optimiert, der Mensch
checkt nur noch ab.

Beispiele:

- **Saisonstart & -ende** (mehr Zuschauer, Opening-Wochen, Playoff-Rennen): TV und
  Revenue hochgewichten. Der Optimizer platziert dort Marquee-Spiele an Premium-Tagen
  und nimmt dafür **bewusst mehr Reise in Kauf** — Reise-Effizienz wird in diesem
  Fenster automatisch nebensächlich, weil TV/Revenue die Energie dominieren.
- **Belastungs-/Stadtfest-Phasen**: Event-Friction hochgewichten, damit Heimspiele
  Großevents (Marathons, Konzerte) in diesem Fenster meiden.

## Wie es funktioniert

Ein **Phasenplan** ist eine Liste von Zeitfenstern, jedes mit **Multiplikatoren** je
Zieldimension. Für ein Spiel an Datum *d* wird der Beitrag jeder Dimension mit dem
Produkt der Multiplikatoren aller *d* abdeckenden Phasen skaliert (Default 1.0 =
neutral). Die Optimierung minimiert die **phasen-gewichtete Energie** — der berichtete
Plan zeigt weiterhin die *tatsächlichen* Werte (wir gewichten, was *priorisiert* wird,
nicht, was *gemessen* wird).

**V1-Dimensionen (pro Spiel lokalisierbar):** `revenue`, `tv`, `friction`. Damit ist
das Haupt-Szenario vollständig bedienbar — inklusive impliziter Reise-Entgewichtung in
TV/Revenue-Fenstern. Eigene Phasen-Hebel für `travel` und `fatigue` (Saison-Aggregate)
sind der nächste Ausbau.

## Benutzung

Phasenplan als JSON (scheduler-editierbar, siehe `data/season_phases_example.json`):

```json
{
  "phases": [
    { "name": "Saisonstart", "start": "2024-03-20", "end": "2024-04-07",
      "multipliers": { "tv": 3.0, "revenue": 2.0 } },
    { "name": "Saisonende",  "start": "2024-09-16", "end": "2024-09-30",
      "multipliers": { "tv": 3.5, "revenue": 2.5 } }
  ]
}
```

```python
from src.phases import PhasePlan
from src.generator_optimizer import optimize_pareto

plan = PhasePlan.load("data/season_phases_example.json")
season, bundle, log = optimize_pareto(start_season, teams, cfg, profile, phase_plan=plan)
```

## Verifiziert

Mit einem TV-gewichteten Profil und einem TV-Boost (×6) im Saisonstart-Fenster steigt
der **TV-Wert im Fenster** gegenüber einem phasenlosen Lauf (gleicher Seed), während der
globale TV-Wert leicht sinkt — die Attraktivität wird also **gezielt ins gewünschte
Fenster verlagert**, ohne neue CBA-Verletzungen. Test:
`tests/test_sprint_3_phases.py::test_phase_plan_shifts_window_tv_up`.

Ohne Phasenplan (`phase_plan=None`) ist das Verhalten **bit-identisch** zum bisherigen
Optimizer — die 68 Pareto-Tests bleiben grün.

## Regler-Dashboard + Feedback-Schleife (echte Zahlen)

`dashboard/phase_tuner.html` (im Browser öffnen) gibt dem Scheduler **einen Regler je
Dimension** (global) plus **Phasen-Regler** (TV/Revenue/Friction pro Fenster), jeweils mit
km-Wechselkurs und kalibriertem erreichbarem Bereich als Vorab-Orientierung.

Der Knopf **„Diesen Plan rechnen"** schließt die Schleife: er schickt die Konfiguration an
den Optimizer (Warm-Start vom realen Plan + gewichtete Pareto-Optimierung) und zeigt die
**tatsächlichen** Werte — global vs. realer MLB-Plan und pro Fenster.

```bash
# API starten (für den Dashboard-Knopf):
uvicorn tools.api:app            # POST /tune/evaluate

# oder direkt per CLI mit der exportierten JSON:
python -m tools.tune_run --config meine_config.json --season 2024
```

Gemessenes Beispiel (TV ×4 im Saisonstart-Fenster, TV-gewichtetes Profil): Fenster-TV
**162 → 231 (+42 %)**, global Reise **−4 %** vs. realer Plan, **0 CBA-Verletzungen**. Wichtig:
die Vorab-Schätzung im Dashboard ist nur grob — die **echten** Effekte (oft deutlich größer)
liefert der Rechnen-Knopf. Kern: `tools/tuning.evaluate_tuning`.

## Kalibrierte Vorab-Schätzungen (gemessen)

Damit das Dashboard schon VOR dem teuren „Rechnen" realistische Werte zeigt, vermisst
`tools/build_calibration.py` den Optimizer an wenigen Stützstellen und speichert eine
kompakte Antwortkurve (`data/phase_calibration.json`), die das Dashboard live interpoliert.

**Methodik (recherchiert, MLB-auditierbar):** Surrogat = **gemessenes Raster + monotone
Interpolation** statt GP/RBF-Black-Box. Begründung: niedrige Dimension, glatte/monotone,
wenige Stützstellen, Auditierbarkeit (die Literatur — Kriging vs. RBF vs. Polynom — kennt
keinen universellen Sieger; treue Interpolation echter Messpunkte ist hier am ehrlichsten).
Wir nutzen die Energie-Struktur: der wirksame Hebel ist der **Phasen-Multiplikator**
(konzentriert die Dimension ins Fenster), kalibriert bei festem starkem Gewicht, 40k Iter.

**Gemessenes Ergebnis (Saison 2024) — ehrlich:**

| | Fenster-TV | Fenster-Revenue |
|---|---:|---:|
| Warm-Start (vs realer Plan) | **+54 %** | **+51 %** |
| Phasen-Multiplikator zusätzlich (mult 1→8) | +1,2 % (sättigt ~mult 4) | ~0 % |

→ **Der große Hebel ist der Warm-Start**, nicht die Phasen-Regler. Der MLB-Plan ist durch 162
Spiele + CBA so eng, dass die Trade-off-Frontier schmal ist. Das Dashboard zeigt das ehrlich
(„Warm-Start +54 %, Regler +1 %") statt eine große Wirkung vorzutäuschen. Für **größere
Regler-Wirkung** müsste der Pareto-Optimizer verstärkt werden (Geo-Move + mehr Iterationen,
sodass er aus dem reise-optimalen Start heraus stärker umstrukturiert) — dokumentierter
nächster Schritt.

Neu vermessen: `python -m tools.build_calibration --dim tv` / `--dim revenue`.

## Nächster Ausbau

- `travel` und `fatigue` als eigene Phasen-Hebel (Saison-Aggregate je Fenster
  attribuieren), damit z. B. „in dieser Hitze-Woche Reise/Ruhe strikt priorisieren"
  als expliziter Regler verfügbar ist (heute implizit über TV/Revenue-Entgewichtung).
- Phasen-UI im Dashboard (Fenster ziehen, Regler je Dimension).
