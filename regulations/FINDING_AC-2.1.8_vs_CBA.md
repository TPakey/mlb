# Befund — „AC-2.1.8 / 13 days away from home" vs. realer CBA-Wortlaut

**Datum:** 2026-06-09 (Sprint 5, Datengrundlage 5.2)
**Schwere:** HOCH — betrifft die Definition einer harten Compliance-Regel und das
gesamte Q10/Sprint-5.4-Thema.

> ## ✅ ENTSCHEIDUNG (2026-06-09, von Jonas bestätigt)
> **„13 days away" ist KEIN Erfordernis — es zählt nur, was in den Regeln steht
> (V(C)(12) / AC-2.1.9 / 20).** Daraus folgt verbindlich:
> 1. **AC-2.1.8 (13) wird von „hart" auf „weiches Qualitätsziel" zurückgestuft**
>    (Roadtrip-Länge minimieren ist gut, aber keine Compliance-Pflicht).
> 2. **Q10 ist damit erledigt/obsolet** — keine strukturelle ≤13-Garantie nötig.
>    Das `xfail` kann entfernt oder zu einem reinen Soft-Metrik-Test umgewidmet werden.
> 3. **Sprint 5.4 Branch-and-Price entfällt als Pflicht-Ziel** (war nur für die
>    ≤13-Garantie nötig). Bleibt optional für echte From-Scratch-Pläne.
> 4. Die harte Compliance ruht allein auf **AC-2.1.9 (20)**, die bereits strukturell
>    garantiert ist. → Compliance-Report/Docs entsprechend bereinigen.

## Worum es geht

Das Projekt führt **„AC-2.1.8 = max. 13 days away from home"** als zentrale
CBA-Reiseregel. Daran hängt der größte Forschungsaufwand des Projekts: der
`xfail`-Test `test_AC_2_1_8_realer_generator_haelt_konsekutive_away_limit`, die
sechs CP-SAT-Tractability-Ansätze (Q10) und der geplante Branch-and-Price in 5.4.

## Was verifiziert wurde

Volltext-Suche im **offiziellen Basic Agreement 2022–2026** (Article V, Scheduling)
sowie Quervergleich mit dem **2017–2021**-CBA:

| Gesucht | Ergebnis im CBA-Volltext |
|---|---|
| „13 days" / „thirteen" | **nicht vorhanden** |
| „road trip" (Längen-Limit) | nur 1× — Article VII (Einzelzimmer im Hotel), **keine** Längenregel |
| „away from home" (Limit) | **nicht vorhanden** |
| konsekutive Spieltage | **20** (V(C)(12)); Heimteam **24** nur bei Regen-Reschedule |
| 2017–2021-CBA, gleiche Klausel | V(B)(12): ebenfalls **„twenty consecutive dates"** |

## Schlussfolgerung

Die Regel **„max. 13 days away from home" ist im maßgeblichen CBA nicht belegbar.**
Die real bindende, dem Konzept am nächsten stehende Klausel ist:

> **V(C)(12): „No Club shall be scheduled […] to play more than twenty consecutive
> dates without an open day."**

Das ist eine **andere Regel**:
- Sie zählt **konsekutive Spieltage** (Workload/Rest), nicht „Tage weg von zu Hause".
- Sie gilt **home wie away** (ein langer Heimstand zählt genauso), nicht nur Roadtrips.
- Das Limit ist **20 (bzw. 24)**, nicht 13.

## Konsequenz für das Projekt — KORRIGIERT nach Code-Review (2026-06-09)

> **Wichtige Selbstkorrektur.** Die erste Fassung dieses Befunds (oben) wurde
> geschrieben, BEVOR ich `src/player_fatigue.py` und `docs/CBA_DEFINITIONS.md`
> gelesen hatte. Der Code zeigt: das Projekt war hier **weiter, als die erste
> Fassung suggerierte.** Richtigstellung:

1. **Die echte CBA-Regel V(C)(12) ist bereits implementiert — als AC-2.1.9.**
   `max_games_without_off_day` (Limit 20) ist äquivalent zu V(C)(12) (≤20 konsekutive
   Spieltage = ≥1 Off-Day je 21-Tage-Fenster) und wird im Generator **strukturell**
   per Pigeonhole (`_periodic_break_days(max_gap=21)`) garantiert. Das Projekt löst
   also NICHT „das falsche Problem" und hat die echte Regel NICHT übersehen.
2. **Das Projekt hat „13" selbst nie als gesichert behauptet.** `CBA_DEFINITIONS.md`
   markiert die 13-Tage-Auslegung ausdrücklich als **„konservative Auslegung" mit
   offenem TODO** („Exakten Wortlaut aus MLB-CBA / MoU bestätigen"). Mein Beitrag ist
   also enger als zunächst formuliert: ich habe via Volltext **bestätigt**, dass 13
   nicht in Article V steht — nicht eine unbemerkte Lücke „entdeckt".
3. **Der refinierte, weiterhin gültige Punkt:** AC-2.1.8 (13) ist genau die Größe,
   um die der gesamte Q10-Tractability-Kampf und der 5.4-Branch-and-Price-Plan geführt
   werden — also um eine **hart erzwungene Garantie für ein Constraint, das das
   Projekt selbst als unbestätigt führt.** Wenn MLB bestätigt „20 (=AC-2.1.9) ist die
   Regel, 13 nicht", dann ist der harte Teil bereits strukturell gelöst und der
   5.4-Aufwand entfällt. Das ist die eigentliche, hochwertige Schlussfolgerung.

## Offen (vor Änderung der Regel-Definition zu klären)

- **Ursprung von „13": weiterhin unbestätigt** (frühere Fassung „geklärt: nur Slang"
  war zu forsch — sie stützte sich auf eine schwache, vermutlich generierte Quelle).
  Belegt ist nur: 13 steht **nicht in CBA Article V** (2022–26 und 2017–21). Ob es in
  einem **MoU / einer MLB-Scheduling-Office-Praxis** existiert, ist **nicht geprüft**
  (nicht öffentlich). Plausibel als operative „13-Game-Gauntlet"-Heuristik, aber das
  ist Interpretation, kein Beleg.
- **Empfehlung:** Mit MLB-Kontakt gegenchecken („Ist 13 days away ein reales
  Erfordernis aus MoU/Praxis, oder ist allein V(C)(12)/AC-2.1.9 maßgeblich?"). Bis
  dahin AC-2.1.8 **als unbestätigte konservative Heuristik führen** (wie der Code es
  ohnehin tut) und 5.4 **nicht** auf die ≤13-Garantie verpflichten, bis bestätigt.

## Quellen
- Basic Agreement 2022–2026, Article V(C)(12): https://registrationz.mlbpa.org/pdf/MLB%20Basic%20Agreement%202022-26.pdf
- Basic Agreement 2017–2021, Article V(B)(12): https://sports-entertainment.brooklaw.edu/wp-content/uploads/2021/01/Major-League-Baseball-Collective-Bargaining-Agreement-2017-2021-reduced.pdf
