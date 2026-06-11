# Scheduler-Operations-Suite — Design & Nutzung

**Stand:** 2026-06-07 (Sprint 3, Anschluss-Block)
**Zweck:** Der eigentliche Job eines MLB-Schedulers/Travel-Ops-Teams **über die
Kalenderoptimierung hinaus** — pro Auswärts-Trip ein operatives Dossier mit
Boden-Routing, Hotel-Empfehlung (inkl. Historie) und einem professionellen
City-Security-/Risiko-Briefing auf MLB-tauglichem Niveau.

Die Suite setzt **auf dem optimierten Saisonplan auf**: Sie nimmt die Auswärts-
Serien eines Teams und erzeugt für jede besuchte Stadt ein einsatzfertiges
Dossier.

## Module

| Modul | Zweck | Datenbasis |
|---|---|---|
| `src/ops_routing.py` | Boden-Routing Flughafen↔Hotel↔Stadion: Straßendistanz, Fahrzeit, Planbarkeit | `teams.json` (Stadion), `team_airports.json` (Flughafen), Stau-/Detour-Parameter |
| `src/ops_security.py` | City-Security-/Risiko-Briefing (saison-bewusst) | `city_ops_profiles.json` |
| `src/ops_hotels.py` | Hotel-Scoring + Empfehlung mit Buchungshistorie | `team_hotels.json` (Club-Daten) |
| `src/ops_dossier.py` | Bindet alles zu Trip-Dossiers je Auswärts-Stadt | Saisonplan + obige |
| `tools/generate_trip_dossier.py` | CLI: Dossier-Report als Markdown | — |

## 1. Boden-Routing (echte Berechnung)

Koordinaten-basiert: Luftlinie (Haversine) × stadt-spezifischer **Umwegfaktor**
(Detour ~1,35) = Straßendistanz; Fahrzeit = Distanz / (freie Geschwindigkeit /
**Stau-Faktor**). **Planbarkeits-Score** (0–1) aus Stau + Korridor-Redundanz.
Stau-Faktoren sind nach realer Metro-Verkehrslage getiert (NYC/LA/Chicago/DC/
Bay/Boston = schwer 2,0; mittlere Metros 1,6; kleinere 1,35). Die Schnittstelle
(`RouteLeg`) ist so gebaut, dass in Produktion eine **Maps-/Routing-API** den
Schätzer 1:1 ersetzen kann.

## 2. Security-/Risiko-Briefing (fakten-basiert, MLB-Niveau)

Fünf Kategorien je Stadt: **Wetter & Naturgefahren** (severity-bewertet, mit
Saison + Dach-Mitigation), **Medizinische Bereitschaft** (Principal Level-I
Trauma-Center + On-Site-EMS-Standard), **Boden-Transport-Risiko**, **Venue- &
Crowd-Security** (Dach/offen, High-Profile-Flag), **Notfall-Framework**
(Evakuierung/Comms/Liaison-Kontakte als Felder).

Das Briefing ist **saison-/monats-bewusst**: nur die im Spiel-Monat aktiven
Klimagefahren fließen in die Gesamt-Severity ein (z. B. St. Petersburg im Juli =
*Hoch* wegen Hurrikan-Saison; im März = *Niedrig*).

**Daten-Ehrlichkeit:** Die regionale Klimatologie und die Level-I-Trauma-Center
sind verifizierbare, stabile Fakten. **Spieltag-spezifische Lage** (aktuelle
Bedrohungseinstufung, On-Call-EMS-Routing, VIP-/Protest-Lage) ist bewusst als
**Liaison-Feld** markiert — diese Daten kommen am Spieltag vom lokalen Law-
Enforcement-/EMS-Kontakt, nicht aus einem statischen Modell. Das Briefing liefert
die belastbare Grundstruktur und markiert klar, was vor Ort zu bestätigen ist —
genau so, wie ein professionelles Travel-Security-Briefing aufgebaut ist (kein
„Kindergarten", aber auch keine erfundene Bedrohungsspezifik).

## 3. Hotel-Empfehlung mit Historie

Score = gewichtete Summe aus **Stadion-Nähe**, **Komfort-Tier**, **Security-Tier**
und **Buchungshistorie** (bewährte „preferred properties" mit gutem Rating werden
bevorzugt; neue Häuser bekommen einen **Audit-Flag**). Beispiel: in Boston wird
das bewährte Back-Bay-Premium-Haus (Score 97, 11 Vor-Aufenthalte, 4,7★) dem
näheren, aber schwächeren Fenway-District-Haus vorgezogen.

**Daten-Ehrlichkeit:** `data/team_hotels.json` ist **illustrativer Seed** (klar
markiert). In Produktion importiert der Club seine **realen Buchungs-/Historie-
Daten** (preferred properties, Raten, Security-Audits) ins selbe Schema — die
Engine ist datenunabhängig und sofort einsatzfähig.

## 4. Trip-Dossier

`team_dossier_report(season, team_id)` erzeugt einen Markdown-Report: eine
**Risiko-Übersicht** aller Auswärts-Städte (Stadt, Termin, Risikostufe,
Transfer-Planbarkeit, empfohlenes Hotel) plus pro Stadt das volle Dossier
(Routing-Tabelle, Hotel-Rangliste, Security-Briefing, High-Profile-Flags für
Rivalitäts-/Feiertagsspiele).

Beispiel: `docs/EXAMPLE_TRIP_DOSSIER_NYY_2024.md` (Yankees 2024, 27 Auswärts-
Städte).

## Nutzung

```bash
# Dossier für ein Team als Markdown:
python -m tools.generate_trip_dossier --team NYY --season 2024 --out output/ops/NYY_2024.md
# Schnell-Check (erste 5 Städte) auf stdout:
python -m tools.generate_trip_dossier --team BOS --season 2024 --limit 5
```

## Was Produktion noch braucht (ehrlich)

- **Hotel-Daten:** Club-eigene Buchungshistorie + Security-Audits ins
  `team_hotels.json`-Schema importieren (Seed ersetzen).
- **Routing:** optional Maps-API statt Schätzer (Schnittstelle steht).
- **Security:** lokale EMS-/PD-Liaison-Kontakte + Spieltag-Lagebild anbinden
  (Felder sind vorgesehen). Genaue Stadion-Koordinaten statt Ballpark-Stadt-
  Koordinaten verfeinern die Routing-Distanzen (kleiner Effekt, vgl. P2-4).
- **Verifikation der Trauma-Center-Routings** mit den jeweiligen lokalen EMS-
  Stellen (Namen sind korrekt; Game-Day-On-Call-Routing bestätigen).
