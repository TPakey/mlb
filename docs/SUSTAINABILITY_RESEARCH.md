# CO₂- und Fairness-Methodik — Quellen & Begründung

**Stand:** Sprint 3 (2026-06-01) · **Module:** `src/sustainability.py`, `src/fairness.py`

Dieses Dokument belegt die in Sprint 3 / Track C eingeführten abgeleiteten Kennzahlen.
**Grundsatz (Charter):** keine erfundenen Zahlen — jeder Faktor ist zitiert; wo wir
vereinfachen, ist die Annahme offengelegt.

---

## 1 — CO₂-Modell (`src/sustainability.py`)

MLB-Teams reisen per **Team-Charter**: ein eigenes Flugzeug pro Trip für Mannschaft,
Staff und Equipment. Deshalb rechnen wir auf **Flugzeug-Ebene** (kg CO₂ pro
Flugzeug-km), nicht pro Passagier — eine Pro-Passagier-Zahl würde die reale
Emissionslast eines Charters massiv unterschätzen.

Der CO₂-Faktor ist das Produkt zweier unabhängig belegter Größen:

| Faktor | Wert | Quelle |
|---|---|---|
| CO₂ je kg Jet-A | **3,16 kg CO₂ / kg Treibstoff** | ICAO CAEP-Standard, ICAO Doc 9889 (1. Aufl. 2011); identisch in CORSIA, EU ETS, ISO. Bestätigt durch EUROCONTROL Standard Inputs. |
| Treibstoff je Flugzeug-km | **3,98 kg / km** (Boeing 737-800) | Wikipedia "Fuel economy in aircraft" — 737-800 als repräsentative Narrowbody (typischer Team-Charter). |

**Abgeleiteter Faktor:** 3,16 × 3,98 = **12,58 kg CO₂ je Flugzeug-km**
(`CO2_KG_PER_KM` in `sustainability.py`).

**Plausibilität:** Bei einer Liga-Gesamtdistanz von ~2,1 Mio km ergibt das
≈ 26.400 t CO₂ pro Saison bzw. ~880 t pro Team — eine plausible Größenordnung für
eine Saison Charter-Flugverkehr über ~70.000 km pro Team.

**Offengelegte Annahme / Limitation.** Reale Team-Flotten mischen 737/757/A321 und
fliegen mit Equipment-Zuladung; einzelne Trips per Boden-Bus (kurze Distanzen) sind
nicht abgezogen. Der Faktor ist daher eine *konservative Single-Type-Näherung*. Bei
besserer Datenlage (flottenspezifischer Mix, Frachtzuschlag, Ground-Travel-Schwelle)
zentral in den Modul-Konstanten aktualisierbar.

---

## 2 — Fairness-Metrik (`src/fairness.py`)

Reine km-Minimierung optimiert die **Summe**, nicht die **Verteilung**. Ein Plan kann
liga-weit weniger fliegen und trotzdem einzelne Teams (oft Westküste) stark
benachteiligen → Wettbewerbsintegrität. Wir messen die Verteilung mit zwei Größen:

**Gini-Koeffizient** der Pro-Team-Reise-km (0 = perfekt gleich, →1 = maximal ungleich).
Standard-Ungleichheitsmaß über die Lorenz-Kurve. Verwendete unverzerrte Sample-Form
für aufsteigend sortierte Werte x₁..xₙ:

```
G = ( 2 · Σ i·xᵢ ) / ( n · Σ xᵢ )  −  (n+1)/n        (i = 1..n)
```

**Disparity-Ratio** = max(km) / min(km) — intuitiv lesbar: "das am meisten reisende
Team fliegt X-mal so weit wie das am wenigsten reisende".

Beide werden als **abgeleitete Report-Kennzahlen** geführt (nicht als 9./10.
Pareto-Dimension), um die bestehende 8-D-`ParetoBundle`-Invariante und alle Tests
stabil zu halten. Eine Aufnahme als weiches Pareto-Ziel ist ein bewusst separates
Folge-Item.

---

## Quellen

- ICAO / CAEP CO₂-Konversionsfaktor 3,16 kg CO₂ / kg Jet-A: ICAO Doc 9889; EUROCONTROL
  Standard Inputs for Economic Analyses — Amount of emissions released by fuel burn.
  <https://ansperformance.eu/economics/cba/standard-inputs/latest/chapters/amount_of_emissions_released_by_fuel_burn.html>
- Boeing 737-800 Treibstoffverbrauch 3,98 kg/km: Wikipedia, "Fuel economy in aircraft".
  <https://en.wikipedia.org/wiki/Fuel_economy_in_aircraft>
- Gini-Koeffizient (Standarddefinition / Lorenz-Kurve): allgemein anerkanntes
  ökonomisches Ungleichheitsmaß.
