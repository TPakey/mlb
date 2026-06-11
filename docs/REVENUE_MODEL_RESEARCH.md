# Revenue-Modell — Recherche und Spezifikation

Recherche-Stand: 2026-05-22

## Wofür wir das brauchen

Sprint 2.2 verlangt eine Tradeoff-Bewertung pro Alternative inklusive
**USD-Impact-Δ** (AC-2.2.4). Wir wollen keinen Black-Box-Score, sondern
ein transparentes, dokumentiertes, ersetzbares Modell, mit dem ein
MLB-Operator den geschätzten Revenue-Effekt einer Schedule-Änderung
nachvollziehen kann.

## Empirische Befunde aus der Recherche

### League-weite Eckdaten 2024

- Liga-Durchschnitts-Auslastung: **28.513 Zuschauer pro Spiel** (-3 % vs. 2023)
- Liga-Gate-Receipts gesamt: **3,41 Mrd. USD** über die gesamte Saison
- Liga-Durchschnitts-Ticket-Preis: **38,02 USD**
- Fan Cost Index (FCI) Liga-Durchschnitt: 240 USD pro Familienbesuch

### Spitzenwerte (Top-Teams 2024)

- Dodgers: 4,3 Mio. USD Ticket-Revenue pro Heimspiel (Auslastung 49.067,
  Avg-Ticket 87 USD)
- Yankees: 4,11 Mio. USD pro Heimspiel (41.631 Avg, 99 USD/Ticket)
- Cubs: ~3 Mio. USD pro Heimspiel (90 USD/Ticket)
- Red Sox: ~2,5 Mio. USD pro Heimspiel (87 USD/Ticket)

### Wochentag-Effekt (relativ zum Saison-Durchschnitt)

- Samstag: **+16 %**
- Sonntag: leicht +
- Freitag: leicht + (mittlerer Effekt)
- Montag/Mittwoch/Donnerstag: nahe Null
- **Dienstag: -11 %** (Wochentag mit niedrigster Auslastung)

### Monats-Effekt

Sommer-Monate (Juni–August) und Wochen mit Schulferien deutlich höher
als Saisonstart (kühles, regnerisches April) und Saisonende (Schulstart,
Football-Saison-Konkurrenz). Quantifizierung: April-Auslastung etwa
**85 %** des Saisonmittels, Juli-August nahe **115 %**, September
**95 %**.

### Tageszeit-Effekt

Abendspiele haben grundsätzlich **höhere Auslastung als Tagespiele**,
außer am Sonntag-Nachmittag (familienfreundliche Slot-Tradition).

### Doubleheader-Spezifikum (kritisch für Sprint 2.2!)

- **2024 gab es kein einziges geplantes Doubleheader.**
- Single-Admission-Doubleheader (ein Ticket, zwei Spiele) **halbieren
  effektiv die Gate-Einnahmen**. Teams vermeiden sie systematisch.
- Split-Doubleheader (zwei separate Tickets, ggf. Stadion-Räumung
  zwischen den Spielen) sind häufiger, aber selten geplant — meist
  Rainout-Reaktion. Bringen nahezu zweifachen Gate-Revenue, aber
  operative Kosten und Spielerbelastung steigen.

→ **Konsequenz für unsere Strategien:** Die ursprünglich angedachte
"Doubleheader-Compression"-Strategie (Sprint-Charter-Entwurf) ist
revenue-feindlich. Wir ersetzen sie durch "Constrained Re-Generate",
die normale Spiele neu verteilt.

## Unser Modell — Spezifikation

```
expected_revenue(game) = base_team[home_team]
                        * weekday_factor[weekday]
                        * month_factor[month]
                        * daypart_factor[is_night_game]
                        * opponent_draw_factor[away_team]
                        * doubleheader_penalty[is_single_admission]
```

**`base_team[t]`:** Team-spezifischer Erwartungsrevenue pro Heimspiel bei
neutralen Bedingungen. Kalibriert aus Statista/Sportico-Daten für
2024 (Range ca. 0,9 Mio. bis 4,3 Mio. USD).

**`weekday_factor`:** {Mo: 0.97, Di: 0.89, Mi: 0.96, Do: 0.98, Fr: 1.05,
Sa: 1.16, So: 1.08}

**`month_factor`:** {3: 0.80, 4: 0.85, 5: 0.95, 6: 1.05, 7: 1.15,
8: 1.12, 9: 0.95, 10: 0.85}

**`daypart_factor`:** {Day: 0.95, Night: 1.02} — außer Sonntag, da
{Day: 1.00, Night: 0.95}.

**`opponent_draw_factor`:** Bonus für populäre Gäste. {NYY: 1.20,
LAD: 1.18, BOS: 1.12, CHC: 1.08, sonstige Rivalen aus eigener Division:
1.05, Rest: 1.00}.

**`doubleheader_penalty`:** {none: 1.00, single_admission: 0.55,
split_admission: 0.90} — split etwas unter 1.0, weil
gleichtägige Konkurrenz die Drop-in-Käufer aufteilt.

## Was wir bewusst NICHT modellieren

- Win-Streak-Effekte, Star-Spieler-Effekte, Promotion-Nights — kurzfristige
  Variabilität, die mit verfügbaren Daten nicht stabil schätzbar ist.
- Wetter (außer indirekt über month_factor) — fließt im Sprint 2 noch
  nicht ein.
- Sekundäre Revenue (Concessions, Merchandise, Parking) — der FCI wäre
  die Quelle, brauchen wir aber für Sprint 2.2 noch nicht. Kommt mit
  Sprint 2.3 (Profile-Switcher).

## Validierung

Wir validieren das Modell gegen 2024-Ist-Daten:

- Modell läuft auf den vollen 2024-Plan, summiert alle Spiele
- Erwartung: Liga-Gesamt-Revenue innerhalb **±10 %** von 3,41 Mrd. USD
- Pro Team: Spitzenteams (LAD, NYY) innerhalb **±15 %** der Sportico-Werte

Das Validierungs-Skript liegt unter `tools/validate_revenue_model.py`.

## Sources

- [Sportico: Dodgers/Yankees Ticket Revenue Lead MLB](https://www.sportico.com/leagues/baseball/2025/dodgers-yankees-mlb-ticket-revenue-1234854483/)
- [Statista: MLB Gate-Ticketing Revenue 2024](https://www.statista.com/statistics/294185/mlb-gate-receipts/)
- [Statista: MLB Average Ticket Price by Team 2024](https://www.statista.com/statistics/193673/average-ticket-price-in-the-mlb-by-team/)
- [Statista: MLB Average Attendance 2009-2025](https://www.statista.com/statistics/235634/average-attendance-per-game-in-the-mlb-regular-season/)
- [Statista: Fan Cost Index 2024](https://www.statista.com/statistics/202611/fan-cost-index-of-the-major-league-baseball/)
- [Team Marketing Report Fan Cost Index](https://teammarketing.com/fancostindex/)
- [Two Circles: Winning, Weekends and Weather](https://twocircles.com/us/articles/winning-weekends-weather/)
- [Owen Aston on Medium: What Days of the Week are Most Popular](https://medium.com/spring-2024-information-expositions/what-days-of-the-week-are-most-popular-for-mlb-games-93d84924c48a)
- [Wikipedia: Doubleheader (baseball)](https://en.wikipedia.org/wiki/Doubleheader_(baseball))
- [Baseball-Reference: 2024 MLB Attendance & Misc](https://www.baseball-reference.com/leagues/majors/2024-misc.shtml)
