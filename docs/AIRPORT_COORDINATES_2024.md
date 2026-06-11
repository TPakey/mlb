# Flughafen- vs. Stadt-Koordinaten im Reisemodell (P2-4)

**Stand:** 2026-06-07 (Sprint 3, P2)
**Frage:** Bringt der Wechsel von Stadtzentrum- auf primäre Metro-Flughafen-
Koordinaten eine messbar bessere Übereinstimmung mit den realen MLB-Reisemeilen?

## Methode

Optionaler Analyse-Layer (`src/airport_analysis.py`,
`tools/compare_airport_distance.py`): Saison-Reise 2024 unter beiden
Koordinaten-Sätzen, verglichen mit den publizierten MLB-2024-Meilen-Ankern
(SEA 47.441 mi, PIT 26.411 mi). Flughäfen je Team in `data/team_airports.json`
(IATA + Referenzkoordinaten).

## Ergebnis (gemessen 2024)

| | Stadt (Default) | Flughafen |
|---|---:|---:|
| Liga-Total | 1.709.835 km | 1.707.179 km |
| Differenz | — | **−0,16 %** |
| Ø |Fehler| vs. publ. Meilen | 0,75 % | **0,72 %** |

Anker im Detail:

| Team | publ. (km) | Stadt | Flughafen |
|---|---:|---:|---:|
| SEA | 76.349 | 76.142 (**−0,27 %**) | 75.797 (−0,72 %) |
| PIT | 42.504 | 43.024 (+1,22 %) | 42.811 (**+0,72 %**) |

## Bewertung & Empfehlung

Der Effekt ist **marginal und gemischt**: Der Liga-Total ändert sich um nur
−0,16 %, der mittlere Anker-Fehler sinkt minimal (0,75 → 0,72 %), aber pro Team
uneinheitlich (Flughafen besser für PIT, leicht schlechter für SEA).

**Empfehlung: Stadt-Koordinaten bleiben der Default.** Sie sind die validierte
Industrie-Standardmethodik („lineare Meilen Stadt↔Stadt", ~1 %), und der
Flughafen-Layer bietet keinen klaren Gewinn, der einen Wechsel (mit Re-Eichung
aller km-Baselines und Determinismus-Prüfung) rechtfertigt. Der Flughafen-Layer
bleibt als **dokumentierte, getestete Option** verfügbar — z. B. falls MLB-Ops
eine flughafen-genaue Charter-Modellierung verlangt oder einzelne Teams (West
Sacramento/Athletics → SMF) eine abweichende Origin-Logik brauchen.

Aufruf: `python -m tools.compare_airport_distance --season 2024`.

## Quellen
- Publizierte MLB-2024-Meilen: `docs/PROJECT_REVIEW_2026-06.md` (P2-4),
  arizonasports.com / Nestico.
- Flughafen-Referenzkoordinaten: Standard-IATA-Flughafendaten (stabile Fakten).
