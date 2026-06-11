# Sprint 5 — Datengrundlage (Tiefen-Recherche)

**Stand:** 2026-06-09. Recherche-Phase als Front-End von Sprint 5.2 (externe Daten).
Referenzjahre: **2024 und 2025** (Double-Check). Prinzip: echte, quellenbelegte Daten,
wo möglich; ehrlich markierte Grenzen, wo öffentlich nicht beschaffbar.

## Qualitäts-Ampel je Datenart

| Datenart | Belastbarkeit | Status |
|---|---|---|
| National-TV-Fenster | 🟢 Struktur hart belegt; Spiel-für-Spiel = Fleißarbeit | Struktur fertig |
| CBA-Reiseklauseln | 🟢 verbatim aus offiziellem Vertrag | fertig + Befund |
| Venue-Belegung | 🟢 strukturelle Hart-Konflikte 2024/25 belegt; Konzert-Kalender = Datenerfassung | Kern fertig |
| Gate-Receipts | 🟡 Liga-Durchschnitt/Ranking öffentlich; exakte Pro-Team-Preise teils paywall | Proxy, ehrliche Grenze |

---

## 1. National-TV-Fenster (🟢 Struktur)

**Kernbefund:** Die TV-Struktur ist in **2024 und 2025 identisch** (der große
Vertragsumbau mit NBC/Netflix greift erst ab 2026). Saubere Jahres-Konsistenz.

Die vier nationalen Fenster und ihre Scheduling-Bedeutung:

| Fenster | Slot | Exklusivität / Scheduling-Wirkung |
|---|---|---|
| **Apple TV+ „Friday Night Baseball"** | Fr, Doubleheader (2 Spiele) | **Exklusiv** — laufen nur auf Apple, nicht auf RSNs. Matchup an Fr-Slot gepinnt. (Ausnahme 2024: Apple gab am 7.6. Dodgers-Yankees lokal frei.) |
| **ESPN „Sunday Night Baseball"** | So ~19:00 ET | Nationales Exklusivfenster. Koppelt an CBA V(C)(8) (Getaway-Ausnahme). |
| **FOX/FS1 „Baseball Night in America"** | Sa (ab Mai) | Mehrere Spiele, Nachmittag + Primetime. |
| **TBS** | Di-Abend | Reguläre Saisonspiele (2024 + Max-Simulcast). |

**Ehrliche Lücke:** Die vollständige Spiel-für-Spiel-Liste pro Fenster über beide
Saisons ist öffentlich auffindbar, aber umfangreich → wird beim Bau des
Ingestion-Loaders gegen `data/mlb_schedule_2024.json` / `2025.json` abgeglichen
(jede TV-Zuordnung trifft auf ein echtes Spiel = bester Qualitäts-Check).

---

## 2. CBA-Reiseklauseln (🟢 verbatim) — mit Korrektur-Befund

Voller Verbatim-Auszug: `regulations/CBA_2022-2026_Article_V_Scheduling.md`.
Die scheduling-relevanten harten Regeln (Article V(C)):

- **V(C)(12):** ≤ **20 konsekutive Spieltage** ohne Off-Day (Heim ≤24 nur bei Regen).
- **V(C)(13):** ≤2 Off-Days/7-Tage; ≥7 Off-Days in den letzten 67 Tagen, ≥3 in 32.
- **V(C)(11):** Off-Day **Pflicht** bei Pacific→Eastern-Reise (≤7 Ausnahmen/Liga).
- **V(C)(8):** Getaway-Startzeit-Formel; **Ausnahme ESPN Sunday Night** → TV-Kopplung.
- **V(C)(17):** All-Star-Break = 4 Tage. **V(C)(14)/(15):** Doubleheader-Limits.

**Kritischer Befund (HOCH):** Die Projekt-Annahme „AC-2.1.8 = max. 13 days away
from home" ist **im CBA nicht belegbar** (weder 2022–26 noch 2017–21). „13 days
from home" ist Umgangssprache für die „13-Game-Gauntlets" (harte Roadtrips, 10–14
Tage) — eine **operative Belastungs-Heuristik, kein Vertrags-Limit**. Das echte harte
Muss ist V(C)(12) (≤20 konsekutiv). → AC-2.1.8 als **weiches Qualitätsziel**
modellieren; **kein Branch-and-Price für eine ≤13-Garantie nötig** (entschärft 5.4).
Voll dokumentiert: `regulations/FINDING_AC-2.1.8_vs_CBA.md`.

---

## 3. Venue-Belegung (🟢 strukturelle Konflikte)

**Befund: 2025 ist ein Sonderjahr mit echten, harten Venue-Konflikten** — ideales
Realdaten-Futter für die VENUE-AVAIL-Mechanik (Sprint 4):

- **Athletics @ Sutter Health Park (West Sacramento), 2025–27.** **Geteilt mit den
  Sacramento River Cats (AAA)** — 14 River-Cats-Heimserien, „dynamic scheduling",
  beide Clubs wechseln sich ab; überwiegend Nachtspiele wegen Hitze. → **harter
  Belegungskonflikt**: wenn die River Cats heim sind, können die A's nicht. Genau
  der VENUE-AVAIL-Fall, datenecht.
- **Rays @ George M. Steinbrenner Field (Tampa), 2025.** Open-Air (Yankees-Spring-
  Training-Park; auch Tampa Tarpons nutzen ihn) → Regen-/Belegungsrisiko im Sommer.
- **2024: Tropicana Field** — Dach von **Hurricane Milton** (Okt 2024) zerstört →
  Auslöser des 2025-Umzugs. Projekt hat bereits ein Milton-Szenario
  (`data/milton_scenario.json`, `tests/test_e2e_milton.py`) — die Realität schließt
  daran an.

**Ehrliche Lücke:** Reguläre Konzert-/Event-Kalender der übrigen 28 Standard-Stadien
sind öffentlich (Venue-Websites/Ticketing), aber als Pro-Stadion-×-2-Jahre-Enumeration
eine Datenerfassungs-Aufgabe → für den Ingestion-Build. Die **dominanten harten
Konflikte 2024/25 sind die geteilten Venues oben** und damit erfasst.

---

## 4. Gate-Receipts-Proxy (🟡 ehrliche Grenze)

**Befund:** Echte Pro-Spiel-Gate-Receipts sind **nicht öffentlich** (bestätigt).
Öffentlich verfügbar:
- **Liga-Durchschnitt:** 2024 ~$38/Ticket (10 J-Hoch). 2023 Fan Cost Index $266,58;
  Ticket-Ø $37; **Marlins günstigste, Yankees teuerste**.
- **Relative Tiers** (Team-Ranking) sind öffentlich; **exakte Pro-Team-Pro-Jahr-
  Preise** liegen bei Team Marketing Report / Statista teils **hinter Paywall**.

**Ehrliche Konsequenz:** Der bestehende Attendance-Proxy (Spearman 0,89) lässt sich
mit öffentlichem **Preis-Ranking/Ø** verbessern (Attendance × Tier-Preis), bleibt aber
ein **Proxy** — keine echten Receipts. Das ist die eine der vier Datenarten, bei der
„im Grunde echte MLB-Daten" öffentlich unmöglich ist; sauber als Proxy markiert.

---

## Empfohlene nächste Schritte

1. **Regel-Modell korrigieren (vor 5.4):** V(C)(12)/20 als verifizierte harte Regel
   ergänzen; AC-2.1.8/13 zu weichem Ziel umwidmen. Mit MLB gegenchecken.
2. **TV + Venue Spiel-für-Spiel** beim Ingestion-Build gegen die echten Schedule-JSONs
   abgleichen (2024 + 2025).
3. **Gate-Receipts:** öffentliche Preis-Tiers einarbeiten, Proxy-Status klar halten.

## Quellen
- TV: [MLB 2024 national broadcast](https://www.mlb.com/news/mlb-national-broadcast-schedule-2024) · [Apple Friday exclusivity](https://www.apple.com/newsroom/2024/03/friday-night-baseball-returns-to-apple-tv-plus-on-march-29/) · [2026–28 rights deals](https://www.mlb.com/news/mlb-announces-media-rights-deals-with-espn-nbc-netflix)
- CBA: [Basic Agreement 2022–26](https://registrationz.mlbpa.org/pdf/MLB%20Basic%20Agreement%202022-26.pdf) · [2017–21](https://sports-entertainment.brooklaw.edu/wp-content/uploads/2021/01/Major-League-Baseball-Collective-Bargaining-Agreement-2017-2021-reduced.pdf)
- Venue: [ESPN: A's/Rays minor-league parks](https://www.espn.com/mlb/story/_/id/44096180/mlb-2025-spring-training-oakland-athletics-tampa-bay-rays-minor-league-ballparks-sacramento) · [Sutter Health Park (Wikipedia)](https://en.wikipedia.org/wiki/Sutter_Health_Park) · [River Cats 2025 schedule](https://www.abc10.com/article/news/local/west-sacramento/sacramento-river-cats-2025-schedule-athletics-sutter-health-park/103-4cd97428-864a-4a2c-9e19-f07fafea32ca)
- Ticketpreise: [Fan Cost Index (TMR)](https://teammarketing.com/fancostindex/) · [Statista: avg ticket 2024](https://www.statista.com/statistics/193426/average-ticket-price-in-the-mlb-since-2006/)
