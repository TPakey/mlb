# Architektur — MLB Logistics Optimizer

## Übersicht

Der Optimizer ist eine modulare Python-Anwendung, die einen Baseline-Spielplan (regelkonform erzeugt oder geladen) gegen ein konfigurierbares Tradeoff-Profil optimiert. Alle Module sind unabhängig testbar und exponieren klare Eingabe-/Ausgabe-Kontrakte.

## Modul-Landkarte

```
                ┌─────────────────────────────────────────┐
                │              src/main.py                │
                │       (CLI · Orchestrierung)            │
                └────────────────┬────────────────────────┘
                                 │
       ┌───────────────────┬─────┴─────┬────────────────────┐
       │                   │           │                    │
┌──────▼─────┐      ┌──────▼──────┐ ┌──▼─────────┐  ┌──────▼─────────┐
│ data_loader│      │  distance   │ │ schedule_  │  │ profiles +     │
│  teams.json│      │  haversine  │ │ generator  │  │ penalties +    │
│  soft.json │      │  + flight   │ │ round-robin│  │ constraints    │
└──────┬─────┘      └──────┬──────┘ └─────┬──────┘  └──────┬─────────┘
       │                   │              │                │
       └────────────┬──────┴──────────────┘                │
                    │                                      │
              ┌─────▼─────────┐                  ┌─────────▼────────┐
              │   scoring     │◄─────────────────│ tradeoff_profile │
              │  multi-score  │                  └──────────────────┘
              │ Travel/Fat/   │
              │ Fair/Bcast/   │
              │ Rev/Wx/Resi   │
              └─────┬─────────┘
                    │
              ┌─────▼─────────┐
              │   optimizer   │   (Simulated Annealing)
              │  3 Move-Typen │
              │  + Hard-Check │
              └─────┬─────────┘
                    │
       ┌────────────┼────────────┐
       │            │            │
 ┌─────▼─────┐ ┌────▼─────┐ ┌────▼──────┐
 │  metrics  │ │ ai_       │ │  dashboard│
 │ (KPI)     │ │ explainer │ │  builder  │
 └───────────┘ └───────────┘ └───────────┘
```

## Modul-Beschreibungen

**`data_loader.py`** — Lädt `teams.json` und `soft_factors.json`, validiert Liga- und Divisionsstruktur (30 Teams, 6 Divisionen à 5 Teams).

**`distance.py`** — Haversine-Distanz zwischen Stadien plus Charter-Flugmodell mit Boden-Overhead und Zeitzonen-Penalty. Erzeugt die globale Distanzmatrix.

**`schedule_generator.py`** — Erzeugt einen Baseline-Plan via Round-Robin (Circle-Methode), gefolgt von Heim/Auswärts-Balancing. Modellannahme: 27 Wochen-Slots, 1 Serie pro Team pro Slot (Vereinfachung gegenüber echter MLB-Struktur, dokumentiert).

**`constraints.py`** — Hard-Constraint-Validator. Prüft Team-Anzahl, Slot-Invariante (jedes Team genau eine Serie pro Slot), Heim/Auswärts-Balance, All-Star-Break-Konflikte, Stadion-Blackouts, lange Auswärtstrips.

**`penalties.py`** — Registry benannter Penalties mit Basis-Werten in km-Equivalent. Penalties enkodieren Liga-Werte (z. B. `BCAST_RIVALRY_HIDDEN` ist mit 500 sehr hoch gewichtet).

**`scoring.py`** — Sieben Score-Kategorien (Travel, Fatigue, Recovery, Fairness, Broadcast, Revenue, Weather, Resilience). Jede Kategorie aggregiert Penalty-Hits und Rohmetriken.

**`profiles.py`** — Sechs vorkonfigurierte Tradeoff-Profile (Balanced, Player Health, Revenue Max, Fan-First, Sustainability, Fairness). Jedes Profil definiert Gewichte pro Score-Kategorie.

**`optimizer.py`** — Simulated Annealing. Drei Neighborhood-Moves (Home-Flip, Intra-Slot-Swap, Inter-Slot-Swap), alle erhalten die Slot-Invariante. Bei jedem Move-Versuch wird zuerst der Hard-Constraint-Validator gefragt; verletzende Moves werden verworfen.

**`metrics.py`** — Berechnet KPIs für Stakeholder-Reports: km, Stunden, Zeitzonen-Hops, CO₂ (5.5 kg/km für Charter), Reisekosten (30 USD/km).

**`ai_explainer.py`** — Generiert eine Markdown-Narrative aus dem Score-Bundle. Architektonisch so vorbereitet, dass `narrate()` gegen einen echten LLM-Call ausgetauscht werden kann.

**`main.py`** — CLI-Einstiegspunkt. Modi: einzelnes Profil (`--profile X`) oder alle Profile vergleichen (`--compare-all`).

## Datenfluss

1. CLI lädt Teams, Soft-Factors und baut Distanzmatrix
2. Baseline-Schedule wird generiert und validiert
3. Initial-Scores werden berechnet
4. Optimizer iteriert mit Simulated Annealing — pro Schritt: Move → Hard-Check → Score → Akzeptanz
5. Final-Scores, Metriken und Narrative werden in `output/<profile>/` abgelegt
6. Dashboard-Builder liest alle Outputs und erzeugt ein eigenständiges HTML

## Erweiterungspunkte

- **Echte MLB-Daten** statt Round-Robin-Baseline: `schedule_generator.py` durch API-Loader ersetzen, der `Schedule`-Objekte liefert.
- **OR-Tools-MIP** statt Simulated Annealing: Optimizer-Interface beibehalten, MIP-Modell als alternative `optimize()`-Implementierung.
- **Echter LLM-Call**: `ai_explainer.narrate()` durch Anthropic-API-Aufruf ersetzen; Score-Bundle ist bereits LLM-freundlich strukturiert.
- **Weitere Profile**: einfach in `profiles.PROFILES` ergänzen.
- **Zusätzliche Penalties**: in `penalties.REGISTRY` definieren, dann in `scoring.*` ausstellen.

## Annahmen und Vereinfachungen

| Bereich | Vereinfachung | Realität |
|---|---|---|
| Schedule-Struktur | 27 Slots × 1 Serie/Team | 162 Spiele in ~54 Serien |
| Off-Days | Nicht modelliert | Etwa 20–25 Off-Days/Team |
| Series-Länge | Fix 3 Spiele | 2–4 Spiele möglich |
| Travel-Modell | Direkte Charter | Charter mit Crew-Limits, FAA-Rules |
| Wetter | Saisonprofile pro Stadt | Echte historische Wetterdaten |
| Broadcasting | Heuristik (Slot mod 2) | Echte Sendetermine FOX/ESPN/Apple |
| Labor Agreement | Max 7 Auswärts-Slots | MLBPA-CBA spezifische Klauseln |

Alle Vereinfachungen sind in den jeweiligen Moduldateien dokumentiert und können durch reichere Modelle ersetzt werden.
