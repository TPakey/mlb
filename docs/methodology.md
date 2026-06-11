# Methodik — MLB Logistics Optimizer

## Leitfrage

> Wie generieren wir einen MLB-Saisonkalender, der Reisedistanzen minimiert, sportlich fair bleibt, Spielergesundheit schützt, TV-/Revenue-Potenzial ausschöpft und gegenüber Störungen robust ist?

## Constraint-Hierarchie

Das System unterscheidet zwei fundamental verschiedene Arten von Bedingungen:

### Hard Constraints — binäre Validierung

Hard Constraints werden NIE verletzt. Verletzung = ungültiger Plan. Beispiele:

- Saisonstruktur (30 Teams, korrekte Heim/Auswärts-Balance, je 5 Teams pro Division)
- Kalender (Saisonfenster, All-Star-Break, max. 1 Serie pro Team pro Slot)
- Stadion-Blackouts (Konzerte, NFL-Sharing, Wartung)
- Travel-Feasibility (Minimum-Transit-Zeit)
- Labor-Agreement (max. aufeinanderfolgende Auswärts-Slots)

Der Validator (`constraints.py`) prüft sie nach jedem Optimizer-Move; verletzende Moves werden verworfen, ohne in die Zielfunktion einzugehen.

> **Wichtig:** Hard Constraints sollten *minimal, stabil, extrem gut definiert* sein. Zu viele machen Optimierung unmöglich. Viele scheinbare Hard Constraints sind in Wahrheit *politische Präferenzen* — die gehören in die Soft Constraints.

### Soft Constraints — gewichtete Optimierung

Soft Constraints sind das, was wir *wollen*, aber bei Bedarf opfern können. Verletzungen erzeugen Penalties. Acht Hauptkategorien:

1. **Travel** — km, Stunden, Zeitzonen-Hops, Ostkurs-Übernachter
2. **Fatigue** — Reisedichte, lange Auswärtstrips, Backstage-Stress
3. **Recovery** — Off-Day-Qualität, Ankunftszeiten
4. **Fairness** — Varianz zwischen Teams (km, Ruhetage, TV-Exposure)
5. **Broadcast** — Marquee-Visibility, Primetime-Qualität
6. **Revenue** — Wochenend-Auslastung, Holiday-Matchups
7. **Weather** — Kalt-/Hitze-Risiko, Hurricane-Fenster
8. **Resilience** — Reparatur-Optionen bei Ausfall

## Penalty-System

Jede konkrete Penalty hat einen eindeutigen Code, einen Namen, einen Basis-Wert in km-Equivalent und einen Kategorie-Tag. Beispiele:

| Code | Name | Basis | Kategorie |
|---|---|---:|---|
| `TRV_EAST_OVERNIGHT` | Westküste→Ostküste Übernachtflug | 180 | travel |
| `TRV_CROSS_COUNTRY_TURNAROUND` | Cross-Country mit <24h Pause | 400 | travel |
| `FAT_COMPRESSED_SCHEDULE` | Doubleheader nach Reisetag | 300 | fatigue |
| `BCAST_RIVALRY_HIDDEN` | Top-Rivalität ausserhalb Primetime | 500 | broadcast |
| `WX_COLD_OPEN_APRIL` | Heimserie in Kaltstadt im April | 120 | weather |
| `WX_HURRICANE_WINDOW` | Heimserie im Hurricane-Risikofenster | 180 | weather |

Die Werte sind transparent, dokumentiert und kalibrierbar. Sie *enkodieren Liga-Werte*: was hoch bestraft ist, ist das, was die Liga wertschätzt.

## Multi-Score-Bundle

Pro Plan-Iteration wird ein `ScoreBundle` berechnet, das alle acht Kategorien als eigene `CategoryScore`-Objekte enthält — jeweils mit aggregiertem Score, Detail-Komponenten (z. B. `total_km`, `timezone_hops`) und Penalty-Hits.

Dies erlaubt dem Stakeholder, die *Quellen* eines Scores zu inspizieren — nicht nur die Aggregat-Zahl.

## Tradeoff-Profile

Ein einziger Optimierungs-Score existiert NICHT. Stattdessen werden die acht Kategorien über ein `TradeoffProfile` zu Gesamtkosten kombiniert. Sechs Profile sind out-of-the-box konfiguriert:

| Profil | Travel | Fatigue | Fairness | Broadcast | Revenue | Weather | Resilience |
|---|---:|---:|---:|---:|---:|---:|---:|
| Balanced | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| Player Health | 1.5 | **3.0** | 1.2 | 0.6 | 0.6 | **2.0** | 1.5 |
| Revenue Max | 0.5 | 0.5 | 0.7 | **2.5** | **2.5** | 0.8 | 0.8 |
| Fan-First | 0.7 | 0.8 | 1.0 | **2.0** | 1.5 | 1.0 | 0.8 |
| Sustainability | **3.0** | 1.2 | 1.0 | 0.7 | 0.7 | 1.0 | 1.0 |
| Fairness | 1.2 | 1.5 | **3.0** | 0.9 | 0.9 | 1.0 | 1.2 |

## Optimierungsalgorithmus

**Simulated Annealing**. Geometrische Abkühlung von T=3000 auf T=5 über typisch 6.000 Iterationen.

Drei Move-Typen erhalten alle die Slot-Invariante:

1. **HOME-FLIP** (20%) — Heim/Auswärts einer Serie tauschen
2. **INTRA-SLOT-SWAP** (50%) — innerhalb eines Slots Partner rotieren
3. **INTER-SLOT-SWAP** (30%) — zwischen zwei Slots Partner austauschen

Akzeptanzregel: ΔE < 0 immer; ΔE > 0 mit Wahrscheinlichkeit exp(−ΔE/T).

## Pareto-Beobachtung

Über alle Profile zeigt sich konsistent: **kein Profil dominiert in allen Dimensionen**. Sustainability minimiert km am stärksten, aber zu Lasten von Fatigue. Revenue Max maximiert TV-Werte, aber bei höherer Reise-Belastung. Die finale Wahl ist *politisch, strategisch, ökonomisch* — keine rein mathematische.

## Validierung

Pro Optimierungslauf erzeugt das System:

- vollständigen Plan als JSON
- Score-Bundle mit Detail-Komponenten
- KPI-Bericht (km, CO₂, Reisekosten pro Team)
- Markdown-Narrative für Stakeholder
- Profil-Vergleichstabelle bei `--compare-all`

Alle Daten sind reproduzierbar (deterministischer Seed) und nachvollziehbar.
