# TV-Slot-Modell — Recherche und Spezifikation

Recherche-Stand: 2026-05-23

## Wofür wir das brauchen

Sprint 2.3 braucht eine **TV-Slot-Score-Dimension** auf der Pareto-Achse —
damit ein MLB-Operator sehen kann: "Wenn ich den Plan auf Travel-min ziehe,
verliere ich wie viele Premium-TV-Slots?"

Das Modell bewertet pro Plan, wie gut die nationalen TV-Slot-Erwartungen
erfüllt werden.

## Die TV-Landschaft 2026

**Drei-Jahres-Mediendeal 2026–2028:** MLB hat 2025 mit ESPN den Vertrag
mutual aufgelöst und Sunday Night Baseball nach 35 Jahren beendet. Neuer
Deal mit ESPN (reduziert), NBC/Peacock und Netflix.

### Die sieben relevanten Slot-Sender

| Sender / Slot | Wann | Anzahl Spiele/Saison | Reichweite |
|---|---|---:|---|
| **Apple TV+ Friday Night Baseball** | Fr 19:00 + 21:30 ET, Doubleheader | ~50 (25 Wochen × 2) | Streaming, 60 Länder |
| **FOX Saturday Baseball Night in America** | Sa 19:00 ET, Primetime | ~24 | Broadcast TV |
| **FOX Saturday Afternoon** | Sa 16:00 ET | ~10–15 | Broadcast TV (regionalisiert) |
| **NBC/Peacock Sunday Night Baseball** | So 19:00 ET | ~27 (31.5.–6.9. + Sondertermine) | Broadcast/Streaming |
| **NBC/Peacock Sunday Leadoff** | So 12:00/13:00 ET | ~18 | Peacock-Streaming |
| **TBS Tuesday Night** | Di 19:00–21:30 ET | ~24 | Cable |
| **MLB Network Showcase** | Do 19:00 ET | ~20 | Cable (MLB-eigen) |
| **ESPN Reduziertes Bundle** | Midweek-fokussiert | 30 (23 davon Juni-August) | Cable |
| **Netflix Special Events** | unregelmäßig | 3 (Opening Night, HR Derby, Field of Dreams) | Streaming |

**Insgesamt ~200 nationale TV-Slots** über die 2.430-Spiele-Saison
= ca. **8 % aller Spiele** sind national gefeatured.

### Schlüssel-Daten 2026

- **Opening Night Netflix:** Yankees @ Giants, 25.03.2026, 20:00 ET
- **Apple TV+ Saisonstart:** 27.03.2026 (LAA @ HOU + CLE @ SEA)
- **FOX Saisonstart:** 28.03.2026 (MIN @ BAL 15:05; NYY @ SFG 19:00)
- **TBS Saisonstart:** 31.03.2026 (NYY @ SEA 21:30)
- **MLB Network Showcase Start:** 02.04.2026 (NYM @ SFG)
- **NBC Sunday Night Baseball:** Hauptsaison 31.05.–06.09.2026 + Special: 12.04. und 30.08.
- **Field of Dreams Game Netflix:** Sondertermin 2026

## Marquee-Matchups (Premium-Status)

Diese Paarungen werden besonders häufig gepicked und liefern überdurchschnittlich
viele nationale Slots:

| Marquee-Matchup | Häufigkeit auf nationalen Slots 2026 |
|---|---|
| **NYY vs BOS** (Yankees–Red Sox) | mind. 4 nationale Termine bestätigt (TBS, NBC, FOX) |
| **LAD vs NYY** (Dodgers–Yankees, WS-Rematch 2024) | mind. 2 |
| **LAD vs SFG** (Dodgers–Giants Rivalry) | mind. 3 |
| **LAD vs PHI** (NLDS-Rematch 2025) | bestätigt 29.05. Apple TV+ |
| **LAD vs SDP** (NL West) | bestätigt 05.07. NBC |
| **LAD vs TOR** (WS-Rematch 2025) | bestätigt 07.04. TBS |
| **CHC vs STL** (Cardinals–Cubs Rivalry) | bestätigt 31.05. NBC |
| **NYY vs NYM** (Subway Series) | Apple TV+ + andere |
| **CHC vs CWS** (Crosstown Classic) | Cubs-White Sox |
| **LAD vs LAA** (Freeway Series) | aktuell rar |

Diese Marquee-Bonus-Liste fließt als `marquee_bonus` in den TV-Score ein.

## Modell-Spezifikation

```
tv_slot_score(season) = Σ über alle Spiele:
    base_slot_value(weekday, daypart) × marquee_multiplier(home, away) × historic_pick_prob(home, away)
```

**`base_slot_value` — Slot-Attraktivität pro Wochentag/Tageszeit:**

| Wochentag | Daypart | Slot-Wert |
|---|---|---:|
| Fr Abend | Night | 1.20 (Apple TV+) |
| Sa Afternoon | Day | 1.10 (FOX afternoon) |
| Sa Primetime | Night | 1.50 (FOX Baseball Night in America) |
| So Mittag | Day | 1.05 (Sunday Leadoff) |
| So Abend | Night | **1.60** (NBC/Peacock SNB, Premium-Slot) |
| Mo–Do | Night | 0.90 (regional / Showcase) |
| Di | Night | 1.20 (TBS Tuesday Night) |
| Do | Night | 1.05 (MLB Network Showcase) |
| Mi | Night | 1.10 (ESPN Midweek) |

**`marquee_multiplier`:** 1.5 für die Marquee-Liste oben, 1.2 für Division-Rivals, 1.0 sonst.

**`historic_pick_prob`:** für jedes Heimteam ein Faktor zwischen 0.7 (kleiner Markt) und 1.4 (LAD, NYY) — historische Wahrscheinlichkeit, national gepicked zu werden.

## Operative Use-Cases für die Pareto-Achse

- **Profile `tv_optimized`** maximiert den TV-Slot-Score: viele
  Marquee-Matchups in Premium-Slots, Heim-Auslastung großer Märkte in
  Wochenend-Primetime.
- **Profile `travel_min`** drückt den TV-Score weil km-Optimum oft
  Marquee-Matchups in suboptimale Slots packt.
- Tradeoff sichtbar: "Wenn wir 80.000 km sparen wollen, verlieren wir
  geschätzt 15 Marquee-Slots" — das ist die Kernfrage, die Sprint 2.3
  beantworten kann.

## Sources

- [Apple Newsroom: Friday Night Baseball 2026](https://www.apple.com/newsroom/2026/03/friday-night-baseball-returns-to-apple-tv-on-march-27-for-its-fifth-season/)
- [Yahoo Sports: MLB Apple TV schedule 2026](https://sports.yahoo.com/articles/mlb-apple-tv-schedule-2026-110001166.html)
- [FOX Sports: 2026 MLB Schedule Press](https://www.foxsports.com/stories/presspass/fox-sports-unveils-2026-major-league-baseball-regular-season-schedule)
- [NBC Sports Press Release: 2026 Sunday Night Baseball Schedule](https://www.nbcsports.com/pressbox/press-releases/ohtani-judge-yankees-red-sox-dodgers-yankees-cubs-cardinals-and-additional-premium-matchups-headline-2026-sunday-night-baseball-schedule-as-major-league-baseball-returns-to-nbc-and-peacock)
- [NBC Insider: MLB Sunday Night Baseball Full 2026 Schedule](https://www.nbc.com/nbc-insider/mlb-sunday-night-baseball-on-nbc-full-2026-schedule)
- [TBS / WBD Press Release: 2026 MLB Tuesday Schedule](https://press.wbd.com/us/media-release/tnt-sports/tnt-sports-announces-first-half-2026-mlb-tuesday-regular-season-schedule-tbs)
- [Yahoo Sports: MLB on TBS schedule 2026](https://sports.yahoo.com/articles/mlb-tbs-schedule-2026-dates-050002052.html)
- [ESPN Press Room: ESPN 2026 MLB schedule reimagined](https://espnpressroom.com/us/press-releases/2025/12/espn-unveils-more-mlb-game-selections-for-key-dates-in-2026/)
- [NBC Sports: 2026 MLB Network Showcase Schedule](https://nationaltoday.com/us/ny/new-york/news/2026/02/02/2026-mlb-network-showcase-schedule-announced/)
- [Netflix Tudum: MLB on Netflix 2026](https://www.netflix.com/tudum/articles/mlb-netflix-opening-day-home-run-derby-field-of-dreams)
- [MLB.com: 3-year media rights deals](https://www.mlb.com/news/mlb-announces-media-rights-deals-with-espn-nbc-netflix)
- [Wikipedia: 2026 Major League Baseball season](https://en.wikipedia.org/wiki/2026_Major_League_Baseball_season)
- [Sunday Night Baseball Wikipedia entry](https://en.wikipedia.org/wiki/Sunday_Night_Baseball)
- [Awful Announcing: 2026 MLB schedule complexity](https://awfulannouncing.com/mlb/schedule-from-fox-tbs-highlight-tv-complexity.html)
