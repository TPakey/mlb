# Hurricane Milton — Gold-Standard für Sprint 2.2

Recherche-Stand: 2026-05-22

## Was passiert ist

Am **9. Oktober 2024** zerstörte Hurricane Milton mit Windgeschwindigkeiten
über 100 mph das Fiberglas-Dach des Tropicana Field in St. Petersburg, FL.
Großteil der Schäden war nicht-strukturell, aber Spielfeld, Sitzplätze,
Videowand, Clubhäuser etc. waren über Wochen dem Wetter ausgesetzt. Die
Reparaturkosten beliefen sich auf rund 60 Mio. USD. Reparaturdauer:
gesamte Off-Season 2024/25 plus die komplette Saison 2025.

## Die echte MLB-Reaktion (gold standard)

**Stadion-Ersatz:** Die Rays spielten die **gesamte 81-Spiele-Heimsaison
2025** im George M. Steinbrenner Field in Tampa — das Spring-Training-Heim
der Yankees und eigentliches Heim der Single-A Tampa Tarpons. Kapazität:
nur 11.026 Sitze (kleinstes MLB-Stadion in 2025), Open-Air.

**Schedule-Front-Loading:** Wegen Florida-Sommerregen wurde der Plan
massiv umstrukturiert:

- **19 von ersten 22 Spielen** zuhause (April)
- **47 von ersten 59 Spielen** zuhause (bis Anfang Juni)
- **37 von ersten 54 Spielen** zuhause
- Nur **16 von 51 Spielen** zwischen Juli und August zuhause
- **69 von letzten 103 Spielen** auswärts

**Series-Swaps:** Zwei Heim-Serien mit den Los Angeles Angels und den
Minnesota Twins wurden in die Frühphase der Saison getauscht (Home-and-Home-Pakete
neu sortiert).

**Spielzeit-Anpassung:** Erstpitch ab Juni von 19:05 auf **19:35 verschoben**,
um Spitzentemperatur und Nachmittagsgewitter zu umgehen.

**Ergebnis:** Trotz Open-Air und Florida — **null Regenausfälle** in der
Heimsaison 2025. Letztes Heimspiel am 21.09.2025. Rückkehr nach Tropicana
für Opening Day 2026 am 06.04.2026.

## Was wir gegen diesen Gold-Standard messen

Unsere drei Sprint-2.2-Strategien werden mit dem **Milton-Szenario** als
Input gefüttert ("Tropicana Field unbenutzbar 2025-04-01 bis 2025-09-30,
alle 81 Heimspiele betroffen"). Wir vergleichen unsere Outputs gegen die
echte MLB-Reaktion entlang dieser Dimensionen:

| Dimension | Echte MLB-Reaktion | Unser Vergleichswert |
|---|---|---|
| Anteil Heimspiele vor Juni | 47/59 ≈ 80 % | Heimspiel-Quote H1 |
| Heimspiel-Anteil Juli/August | 16/51 ≈ 31 % | Heimspiel-Quote H2 |
| Reise-km Rays 2025 (geschätzt) | recherchieren | km_total für TBR |
| Geänderte Spiele insgesamt | alle 81 + Series-Swaps | diff_count |
| Tatsächliche Rainouts 2025 | 0 | n/a (wir modellieren nicht) |
| Revenue-Δ vs. Baseline-Trop-2025 | ca. -30 % (Kapazität) | revenue_delta_usd |

Das gibt uns eine Story, die ein MLB-Stakeholder versteht: *"Unsere
Strategie X liegt 12 % näher am Front-Loading-Ideal als MLBs eigene
Lösung", "Unsere Strategie Y spart 18.000 km Reise gegenüber MLB,
allerdings auf Kosten von Y-Revenue."*

## Sources

- [FoxWeather: Tropicana Field damage photos](https://www.foxweather.com/weather-news/photos-tampa-bay-rays-tropicana-field-hurricane-milton)
- [Weather.com: Tropicana Field restored](https://weather.com/sports-recreation/news/2026-04-06-hurricane-milton-tropicana-field-tampa-bay-rays-return)
- [ESPN: Steinbrenner Field transformation](https://www.espn.com/mlb/story/_/id/44416191/mlb-2025-tampa-bay-rays-new-york-yankees-steinbrenner-field-transformation)
- [Wikipedia: 2025 Tampa Bay Rays season](https://en.wikipedia.org/wiki/2025_Tampa_Bay_Rays_season)
- [DRaysBay: Rays to Steinbrenner](https://www.draysbay.com/2024/11/14/24296516/tampa-bay-rays-to-play-home-games-at-steinbrenner-field-for-the-2025-season)
- [Boston Globe: Rays schedule reshuffle](https://www.bostonglobe.com/2024/11/25/sports/mlb-rays-schedule-changes-rain/)
- [SI Fannation: MLB Adjusts 2025 schedule](https://www.si.com/fannation/mlb/fastball/news/mlb-adjusts-2025-schedule-to-account-for-tampa-bay-rays-temporary-outdoor-stadium-george-m-steinbrenner-field-tropicana-field-roof-hurricane-milton-angels-twins-home-and-home-01jdjekg5tbm)
- [FOX 13 Tampa Bay: 2025 home schedule wrap-up](https://www.fox13news.com/news/tampa-bay-rays-wrap-up-2025-home-schedule-no-rainouts-steinbrenner-field)
- [Bay News 9: Steinbrenner Field start times](https://baynews9.com/fl/tampa/news/2025/01/17/rays--announce-start-times-for-home-games-at-steinbrenner-field)
