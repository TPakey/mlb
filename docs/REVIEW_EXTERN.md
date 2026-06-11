# Externes Code-Review — MLB Logistics Optimizer

**Reviewer:** Externe Perspektive (Claude, frischer Blick auf das Repo)
**Datum:** 2026-05-27
**Stand des Codes:** Sprint 2.6 abgeschlossen, Sprint 2.7 in Vorbereitung
**Scope:** Algorithmische Korrektheit · Datenmodell-Realitätstreue · Production-Readiness
**Modus:** Nur dokumentieren, keine Code-Änderungen

---

## Zusammenfassung

Das System ist beeindruckend dokumentiert, hat einen sauberen Sprint-Audit-Trail und liefert für Seed 42 reproduzierbare Ergebnisse. Der Architektur-Ansatz (CP-SAT für Feasibility + SA für Multi-Objective) ist akademisch fundiert und richtig gewählt.

**Aber:** Bei einem MLB-Realeinsatz fallen mehrere Befunde auf, die jeweils einzeln das Vertrauen in die Ergebnisse untergraben können. Drei davon (C1, C2, C3) sind so schwerwiegend, dass ich sie vor jeder Stakeholder-Präsentation fixen würde — sie sind **echte Definitionsfehler**, nicht nur Performance- oder Style-Themen. Bei C1 misst das System eine *andere* Größe als das CBA verlangt; bei C2 vergibt der TV-Score systematisch falsche Slots an mehr als die Hälfte aller Spieltage; bei C3 widerspricht der Dokstring dem ausgeführten Code, was den oft zitierten "Pigeonhole-Beweis AC-2.1.8" zu einem Beweis für eine andere Aussage macht.

Insgesamt: **3 Critical, 9 Major, 12 Minor, 6 architektonische Aufräum-Punkte**.

| Severity | Was es bedeutet |
|---|---|
| **Critical** | Falsche Ergebnisse, die als korrekt präsentiert werden. Vor MLB-Übergabe fixen. |
| **Major** | Ergebnis bleibt funktional, aber systematisch verzerrt oder fragil. Vor Produktion fixen. |
| **Minor** | Korrektheit nicht betroffen; Code-Qualität, Wartbarkeit, Dokumentation. |
| **Aufräumen** | Strukturelle Altlasten (Dead Code, Doppel-Implementierungen) — riskant, weil Verwechslungsgefahr. |

---

# CRITICAL — vor MLB-Übergabe fixen

## C1 — AC-2.1.8 misst nicht das, was die CBA-Regel meint

**Datei:** `src/player_fatigue.py:29–62` (`max_consecutive_away_days`), und parallel in `src/generator_optimizer.py:208–250` (`_team_max_streaks`)

**Was der Code tut:** Zählt die längste Folge **konsekutiver Kalendertage mit Auswärts-Spiel**. Sobald ein Off-Day in der Mitte einer Roadtrip liegt, wird der Streak auf 1 zurückgesetzt:

```python
elif (g.date - cur_date).days == 0:
    pass   # Doubleheader
else:
    # Off-Day(s) dazwischen - Streak endet
    cur_streak = 1
```

**Was die CBA-Regel meint:** "No more than X consecutive days away from home." Das ist die Länge einer **Road Trip** als zusammenhängender Block, in dem das Team nicht zu Hause ist — Off-Days *mitten in der Reise* zählen mit dazu, weil das Team auch dann auf Achse und im Hotel ist.

**Reproduktion:**

```
Tag 0  Auswärts BOS
Tag 1  Auswärts BOS
Tag 2  Off-Day  (Team noch in/zwischen BOS und BAL)
Tag 3  Auswärts BAL
Tag 4  Auswärts BAL
```

Echte Roadtrip-Länge: **5 Tage** weg von zu Hause.
Code-Output: `max_consecutive_away_days = 2` (verifiziert per Aufruf in dieser Review).

**Folge:** Sämtliche Aussagen "AC-2.1.8 erfüllt: max ≤ 13" im Repo sind unter einer schwächeren Definition als das echte CBA-Limit. Das System kann unter realer Definition Roadtrips von 16–20+ Tagen produzieren und sie als "≤ 13" verbuchen. Der `test_off_day_breaks_streak` in `tests/test_fatigue_constraints.py:80–88` *zementiert* diese falsche Definition als Soll-Verhalten.

**Folge auf das gesamte System:**
- SA-Penalty bei λ=1M wirkt auf eine Definition, die das Problem unterzählt → die "0 Violations" sind nicht 0 unter echter Definition.
- ParetoBundle.`max_away_streak` ist systematisch zu klein.
- Column-Generation's AC-2.1.8-Constraint in `pricing_subproblem` (`column_generation.py:301–313`) verwendet eine 14-Tage-Fenster-Bedingung "wenn alle 14 Kalendertage gespielt werden, ≥1 Heimspiel". Die ist konsistent mit der CODE-Definition, aber genauso falsch wie der Code.

**Vorschlag (nur dokumentiert):**
1. Definition klären: Was *genau* steht in der MLB-CBA? Wenn es "13 days away from home" heißt, dann muss zwischen zwei Auswärtsspielen ohne dazwischenliegendes Heimspiel gezählt werden — Off-Days dazwischen zählen DAZU.
2. Algorithmus: über das Liste von "Heim-Daten" iterieren; jeder Block zwischen zwei Heim-Daten ist eine Roadtrip mit Länge `next_home - prev_home - 1` (in Tagen, ohne die Heimspiel-Tage selbst). Plus Sondertufallen für Saisonanfang/-ende (zählt das als zu Hause beginnen?).
3. Den Test `test_off_day_breaks_streak` an die neue Definition anpassen — oder explizit ein zweites Constraint einführen ("max konsekutive Auswärts-Spieltage", als Proxy) und im Bundle beide Größen führen, mit klarer Doku, was welche misst.

---

## C2 — TV-Slot-Heuristik unterbewertet Sunday Night Baseball und überbewertet Saturday Day-Games systematisch

**Datei:** `src/tv_slots.py:42–43, 142–144`

**Was der Code tut:**

```python
_DAY_WEEKDAYS: FrozenSet[int] = frozenset({6})   # Sonntag

def _daypart_for_weekday(weekday: int) -> str:
    return "day" if weekday in _DAY_WEEKDAYS else "night"
```

→ **Jedes** Sonntag-Spiel wird als "day" gewertet. **Alle anderen** Wochentage als "night".

**Was in `data/tv_slots.json` steht:**

| Weekday | day-Wert | night-Wert |
|---|---|---|
| 5 (Sa) | 1.1 (Fox Saturday Afternoon) | 1.5 (Fox Saturday Night) |
| 6 (So) | 1.05 (Peacock Sunday Leadoff) | **1.6 (NBC Sunday Night — Premium)** |

**Verifizierter Effekt:**
- Jedes Sonntag-Spiel bekommt 1.05. Der gesamte 1.6er Premium-Slot "NBC Sunday Night Baseball" wird in der Score-Berechnung nie vergeben.
- Jedes Samstag-Spiel bekommt 1.5. Saturday-Day-Games (die historisch jeden Samstag laufen) werden mit dem Night-Wert überbewertet.

**Folge:**
- Der `tv_slot_score` als Pareto-Dimension misst etwas anderes als die Datei behauptet. Das "tv_optimized"-Profil optimiert in die falsche Richtung.
- Das im Review prominente "Ergebnis 2858.8 / 107 Marquee-Spiele" ist mit dieser kaputten Heuristik berechnet.
- MLB-Stakeholder werden sehr schnell merken, dass NBC Sunday Night Baseball nicht modelliert ist — das ist eines der wichtigsten Inventory-Stücke der Liga.

**Vorschlag (dokumentiert):**
- Game-Start-Time aus der MLB Stats API ziehen (das ist die im README angekündigte Quelle) und Daypart daraus ableiten.
- Übergangsweise eine bessere Heuristik: vom Solver gezielt für `slot_value(weekday, "night") > slot_value(weekday, "day")`-Slots zu wählen ist eigentlich eine *Optimierungs*-Entscheidung, keine reine Lookup-Heuristik. Stattdessen: pro Heimspiel-Tag eine Mischwahrscheinlichkeit modellieren (z.B. 70% night, 30% day für Samstag), oder direkt eine zweite Entscheidungsvariable `daypart[g] ∈ {day, night}` im SA aufnehmen.
- Bis die echte Game-Time geladen werden kann, sollte die Limitation im Bundle-Output prominent angezeigt sein — nicht versteckt im Doku-Sprint-Review.

---

## C3 — Pigeonhole-"Beweis" AC-2.1.8 im Dokstring widerspricht dem Aufruf

**Datei:** `src/generator.py:105–127` (`_periodic_break_days`) versus `src/generator.py:459` (Aufruf)

**Was der Dokstring behauptet:**
```
Garantiert via Pigeonhole:
- AC-2.1.8: max 13 konsekutive Away-Tage (Break unterbricht jeden Streak)
- AC-2.1.9: max 20 Spieltage in 21-Tage-Fenster
...
Beweis AC-2.1.8: Jeder Away-Streak wird spaetestens nach max_gap-1=13
Tagen durch den naechsten Break unterbrochen. ✓
```

**Was im Code passiert:**
- Die Default-Signatur ist `max_gap: int = 14` — der Beweis stimmt nur für *diesen* Wert.
- Der tatsächliche Aufruf-Pfad ist `_periodic_break_days(total_days, max_gap=21)` (in `generate()`, Zeile 459).
- Verifizierte Breaks bei `total_days=100`: `[20, 41, 62, 83]` — Abstand 21 Tage zwischen Breaks.
- Pigeonhole für AC-2.1.8 (13 Away-Tage) **gilt nicht** bei `max_gap=21`. Garantiert wird nur AC-2.1.9 (20 Spieltage in 21 Tagen).

**Was tatsächlich AC-2.1.8 erzwingt:** der SA-Penalty mit λ=1.000.000 in der zweiten Stufe (`generator.py:576`).

**Warum das ein Critical ist:**
- Wer die Funktion im Review/Dokstring liest, glaubt an einen mathematischen Beweis für AC-2.1.8. Es gibt keinen. AC-2.1.8 wird **stochastisch** durch SA erzwungen (mit P(accept) ≈ 0), kombiniert mit der *kaputten* Definition aus C1.
- Im `GESAMTBERICHT_FUER_REVIEW.md` taucht genau diese falsche Beweisstruktur als Argument für die finale Lösung auf ("Mechanismus 1 (AC-2.1.9): Periodische Break-Days im CP-SAT" + "Mechanismus 2 (AC-2.1.8): SA mit λ = 1.000.000"). Das ist korrekt für AC-2.1.9, aber der Dokstring von `_periodic_break_days` behauptet trotzdem, *die* Funktion garantiere AC-2.1.8.

**Vorschlag:** Dokstring auf den tatsächlich verwendeten Modus reduzieren ("Garantiert AC-2.1.9 strukturell. AC-2.1.8 wird in Stufe 2 weich erzwungen — siehe `optimize_travel` mit λ=1e6.") und den Default-Wert auf 21 setzen, damit niemand versehentlich mit der 14er-Variante aufruft und glaubt, beide ACs strukturell zu garantieren.

---

# MAJOR — vor Produktion fixen

## M1 — `w_off_day` wird im SA-Move-Update absichtlich ignoriert

**Datei:** `src/generator_optimizer.py:687–702`

In `_energy_from_state()` ist die Linie für `w_off_day` auskommentiert mit Begründung "skip während SA (ändert sich bei const. Spielanzahl kaum)". `ParetoProfile.compute_energy(bundle)` in `src/profiles.py:144–153` enthält `w_off_day` aber sehr wohl.

**Folge:** Das SA optimiert eine *andere* Energiefunktion als das, was als "Profil-Energie" verkauft wird. Profile wie `player_friendly` (w_off_day=50.000.000) bekommen ihre stärkste Gewichtung silently ignoriert. Die finale `compute_pareto_bundle` enthält off_day_variance — also wird der Pareto-Filter mit einem Wert filtern, den das SA gar nicht optimiert hat. Das verzerrt die Frontier zugunsten von Profilen, die nicht auf w_off_day setzen.

**Vorschlag:** Off-Day-Varianz ist tatsächlich teuer, weil sie nicht inkrementell aus dem State herauszurechnen ist. Eine günstigere Proxy-Größe wäre die *Varianz der Spieltag-Lücken*, die inkrementell pro betroffenes Team berechnet werden kann. Oder: Linie aktiv aktivieren und einmal pro `k=50` Iterationen voll neu berechnen.

## M2 — Timezone-Hops ignorieren DST komplett

**Datei:** `src/distance.py:23–30`

`TIMEZONE_OFFSET` enthält reine Standard-Time-Offsets. Phoenix bleibt ganzjährig UTC-7, der Rest der USA wechselt zwischen Standard-Time und Daylight-Saving-Time.

**Verifizierte Konsequenz (in der Review-Session ausgeführt):**
- NY → Phoenix wird *immer* mit 2 Timezone-Hops berechnet. Im Sommer wären es 3 (NY = UTC-4, Phoenix = UTC-7).
- LA → Phoenix wird *immer* mit 1 Hop berechnet. Im Sommer wären es 0.

MLB spielt **fast ausschließlich** im Zeitraum, in dem DST aktiv ist (Ende März bis Anfang November). Jeder Reise-Score für ARI-Spiele ist also strukturell falsch. Der Fehler hat Vorzeichen — d.h. das System hat eine systematische Präferenz oder Aversion gegen Arizona-Reisen.

**Vorschlag:** Mit `zoneinfo` (stdlib seit 3.9) den effektiven UTC-Offset zum konkreten Spieldatum berechnen statt einem statischen Lookup. Der `tz_hops`-Wert wird dann pro Reise-Segment dynamisch — was korrekt ist, weil zwei Reisen in unterschiedlichen Monaten unterschiedliche Hops haben können.

## M3 — `whatif_force_series` kann doppelt buchen

**Datei:** `src/whatif.py:450–462`

Im "neue Serie einfügen"-Branch (wenn `target_games` leer ist, weil im aktuellen Plan kein NYY@BOS existiert):

```python
else:
    # Neue Serie einfügen
    base_pk = max((g.game_pk for g in season.games), default=5_000_000) + 1
    new_games = [
        Game(... home=home, away=away, ...) for i in range(length)
    ]
    modified = _replace_games(modified, [], new_games)
```

Es wird **nicht geprüft**, ob die beteiligten Teams am `forced_start` schon ein anderes Spiel haben. Wenn NYY am 4. Juli z.B. NYY@LAA spielt, fügt der Code eine zweite Serie NYY-vs-BOS am 4. Juli ein, ohne die NYY@LAA-Spiele zu verschieben. Resultat: NYY hat zwei Spiele am selben Tag (kein Doubleheader im definitiven Sinn — zwei *verschiedene Gegner*).

Das wird durch `compute_pareto_bundle` nicht detektiert, weil `_validate_constraints` nur AC-2.1.8/9 prüft, nicht "kein Team ist zweimal gebucht".

**Vorschlag:** Vor dem Einfügen die `colliding_games`-Logik auch im `else`-Branch fahren, oder eine generelle Vorprüfung am Anfang, ob `home` oder `away` an einem der forced_days schon involviert sind.

## M4 — `_find_free_slot` ignoriert All-Star-Break

**Datei:** `src/whatif.py:229–279`

Die Funktion prüft `blackout`, Season-Grenzen und Team-Belegung, aber nicht `season.all_star_dates`. In `whatif_blackout` und `whatif_force_series` kann ein verschobenes Spiel im All-Star-Break landen — ohne Warnung.

**Vorschlag:** `_is_free` um `if d in season.all_star_dates: return False` ergänzen, alternativ als optionalen Parameter durchreichen.

## M5 — `repair_local` löscht "unreschedulable" Spiele, statt sie zu behalten

**Datei:** `src/repair_local.py:172–180`

Der Dokstring sagt:
> "zurueck in occupied legen (Spiel bleibt formal an Originalplatz, aber wir markieren es als unreschedulable)"

Tatsächlicher Code:
```python
if slot is None:
    occupied[g.home].add(g.date)
    occupied[g.away].add(g.date)
    unreschedulable.append(g)
    continue          # → Spiel kommt NICHT in new_games
```

Das Spiel verschwindet komplett aus der Season. Die Game-Anzahl sinkt. Downstream (Travel-Report, Revenue-Report) wird mit weniger Spielen gerechnet, aber `unresolved`-Score wird zwar als hard_constraint_violations gemeldet, nicht aber die Tatsache, dass jetzt insgesamt weniger Spiele existieren.

Im Hurricane-Milton-Test wird das als "26 ungelöste Spiele" verbucht — diese 26 Spiele sind im neuen `season.games` schlicht weg. Wenn jemand die Season anschließend für die Revenue-Berechnung verwendet, wird der Revenue ohne diese 26 Spiele berechnet, also künstlich zu niedrig.

**Vorschlag:** Entweder die Spiele wirklich an Originalposition behalten (mit einem `unreschedulable=True`-Flag) ODER den Dokstring an den Code anpassen UND Downstream-Code (z.B. Score-Bundle) klar darüber informieren, dass die Season ein "Teil-Plan" ist.

## M6 — Pareto-Frontier kann komplett leer werden

**Datei:** `src/pareto.py:98–119, 287–325`

`filter_dominated` filtert nur Pläne mit `is_valid()` (== `constraint_violations == 0`). Wenn das SA bei einem ungünstigen Seed oder einem aggressiven Profil keine violations-freie Lösung findet, sinkt die Anzahl der nicht-dominierten Pläne. Der `while`-Loop mit `max_extra=14` versucht neue Random-Profile, kann aber konzeptionell auch dauerhaft leere Frontiers produzieren — und gibt dann eine `ParetoFrontier(points=[])` zurück, ohne einen Fehler oder eine Warnung zu werfen.

`best_by()` würde dann auf `min/max([])` laufen und einen ValueError werfen — *nicht* im Lib-Code, sondern im aufrufenden Code. Schlimmer: das Demo-Skript `tools/demo_pareto.py` verlässt sich auf eine non-leere Liste.

**Vorschlag:** Wenn `len(non_dominated) == 0`, entweder eine sinnvolle Diagnose werfen (welche AC verletzt? welcher Anker war am nächsten dran?) oder einen Fallback aktivieren, der `violations_penalty` temporär weiter erhöht und einen "least-bad"-Plan zurückgibt.

## M7 — Pareto-Anker starten alle vom identischen Baseline-Plan

**Datei:** `src/pareto.py:248–268`, Doku Zeile 14–17

Design-Entscheidung im Dokstring: "Alle SA-Läufe starten vom selben Baseline-Plan → keine HAP/Phase-B-Wiederholung pro Run; spart 23s × N_profiles."

**Konsequenz:** Wenn das SA für jedes Profil aus demselben Basin startet, konvergieren die Profil-Anker in verwandte lokale Minima desselben Basins. Echte Pareto-Front-Sampling (z.B. NSGA-II) startet diversifiziert. Die "≥ 7 nicht-dominierte Pläne" sind in der Praxis vermutlich 7 leichte Variationen desselben Plans, nicht 7 strukturell unterschiedliche Alternativen.

Das ist ein **Performance/Diversität-Tradeoff**, kein Bug — aber für die Pareto-Story gegenüber MLB ist Diversität wichtiger als Geschwindigkeit, und der aktuelle Default geht in die falsche Richtung.

**Vorschlag:** Optional pro Profil einen leicht unterschiedlichen Start-Seed für CP-SAT verwenden, oder vor dem SA pro Profil einen "Pre-Optimization-Burst" mit 1k Iterationen aus dem Anker-Profil als Bias laufen lassen.

## M8 — `_no_team_overlap` ist O(N) pro SA-Move

**Datei:** `src/generator_optimizer.py:190–203`

Die Funktion sortiert/iteriert `team_idx[team]` für beide Teams und prüft jeden anderen Eintrag auf Tag-Überlappung. Bei ~54 Series pro Team und 2 Teams pro Move sind das ~100 Set-Intersection-Operationen pro Move. Über 700k Iterationen merkt man das.

Wichtiger: bei einem Bench-Worst-Case (höhere Iterations für bessere Konvergenz, wie `enforce_fatigue_constraints=True` praktisch erfordert) skaliert das schlecht.

**Vorschlag:** Sorted-Intervals pro Team führen (durch SA-Moves inkrementell update), dann ist Overlap-Check O(log N) via Binary Search auf der sortierten Start-Day-Liste.

## M9 — Revenue-Modell-Kalibrierung: Division-Rival-Bonus stapelt nicht

**Datei:** `src/revenue.py:108–115`

```python
if game.away in model.opponent_draw_factor and game.away not in ("default", "division_rival_bonus"):
    of = model.opponent_draw_factor[game.away]
else:
    of = model.opponent_draw_factor.get("default", 1.0)
    if division_rivals and game.away in division_rivals.get(game.home, set()):
        of = model.opponent_draw_factor.get("division_rival_bonus", of)
```

Wenn NYY (1.2) der Gegner ist UND zugleich Division-Rivale (z.B. NYY@BOS), greift nur der NYY-Faktor (1.2). Der Rivalitäts-Bonus (1.05) wird *nicht* zusätzlich angewandt. Das unterzählt Marquee-Rivalitäten wie BOS-NYY, was Revenue **und** TV-Score gegen reale Erwartung verzerrt.

**Vorschlag:** `of = base_of * (rival_bonus_factor if is_rival else 1.0)` als multiplikative Kombination, mit klarem Stack der Faktoren in der Doku.

---

# MAJOR — Architektonisch & Code-Health

## M10 — Drei parallele Code-Pfade für Schedule-Erzeugung

Im `src/`-Verzeichnis koexistieren:

1. **Alt (Sprint 0/1):** `schedule_generator.py` (vereinfachtes Slot-Modell) + `optimizer.py` (alte 7-Dim-Profile) + `scoring.py` + `constraints.py` + `validation.py`. Imports: `main.py`, `metrics.py`, `soft_factors.py`, `ai_explainer.py`, `tests/test_end_to_end.py`, `tools/validate_season.py`.
2. **Hauptpipeline (Sprint 2.1+):** `generator.py` + `generator_optimizer.py` + `generator_constraints.py` + `validation_v2.py`.
3. **Akademisch korrekte Alternative (Sprint 2.3a):** `two_phase_pacing.py` + `column_generation.py` + `series_matching.py` + `two_phase_repair.py`.

Alle drei produzieren `Season`-Objekte, alle drei haben ein eigenes Validitätsverständnis (alt: 7-Dim-Profile, neu: 8-Dim ParetoBundle, Sprint 2.3a: nur Phase-A/B). Bei einer MLB-Übergabe musst du klar sagen, welcher Pfad der "richtige" ist — und gleichzeitig erklären, warum die anderen zwei noch da sind.

**Risiko in der Praxis:** `main.py` ruft die ALTE Pipeline auf (`optimizer.optimize`). Wer `python -m src.main` ausführt, bekommt nicht das System, das die Reviews beschreiben. Das fällt sofort negativ auf.

**Vorschlag:** Vor MLB-Demo den toten Pfad (alte Pipeline) entweder strikt unter `src/legacy/` verschieben oder löschen, und `main.py` auf die aktuelle Pipeline umstellen. Test-Suite gleichzeitig aufräumen (`test_end_to_end.py` benutzt die alte Pipeline).

## M11 — Dead Code im Hauptpfad

**Datei:** `src/generator.py:155–292, 295–430`

Zwei umfangreiche Funktionen, die nirgends aufgerufen werden:
- `_repair_fatigue_violations` (~140 Zeilen)
- `_greedy_starts_with_fatigue` (~135 Zeilen, EDF-Greedy aus Sprint 2.3-Iteration)

Beide sind im `generate()`-Pfad nicht erreichbar. Sie stammen aus fehlgeschlagenen Implementierungs-Versuchen und sind im `GESAMTBERICHT` als "fehlgeschlagene Ansätze" beschrieben.

In einem Production-Repo gehört das in `git history`, nicht in den Code. Wer in `generator.py` liest, glaubt, sie würden noch laufen.

## M12 — Toter `if series_starts is None:`-Branch

**Datei:** `src/generator.py:472–479`

```python
series_starts: Optional[List[int]] = None
...
if series_starts is None:        # immer wahr
    ...                          # ganze CP-SAT-Logik hier drin
```

Die Bedingung ist immer `True`, weil `series_starts` direkt darüber auf `None` gesetzt wird und vorher keine andere Schreibung möglich ist. Wahrscheinlich Überrest aus einem früheren Multi-Strategie-Layout. Reine Lesbarkeits-Schuld, kein Bug.

---

# MINOR — Korrektheit OK, aber Verbesserungspotenzial

## N1 — `GeneratorConfig.all_star_break: Tuple[date, date] = None`
Type-Hint widerspricht Default-Wert. Sollte `Optional[Tuple[date, date]] = None`. (`src/generator.py:35`)

## N2 — Keine Eingangsvalidierung in `GeneratorConfig`
Falls `season_end < season_start`: `_season_days()` liefert negative Tage, der ganze Pipeline-Pfad schlägt mit Index-Errors fehl. Saubere Pre-Validation mit klarer Fehlermeldung wäre billig.

## N3 — `_doubleheader_type` returnt immer "split_admission"
**Datei:** `src/revenue.py:75–85`. Single-Admission-Doubleheader (häufiger als gedacht in MLB) werden ignoriert. Das macht den `doubleheader_penalty[single_admission]=0.55` totes Modell-Gewicht.

## N4 — `_is_night_game` ohne echte Spielzeit
**Datei:** `src/revenue.py:64–72`. Heuristik "alles außer Sonntag = night" ist mit den TV-Slot-Werten konsistent — leidet aber unter demselben strukturellen Problem wie C2. Bei einem Lookup der echten Start-Time wäre beides gefixt.

## N5 — `_random_profile` benutzt Standard-Simplex-Sampling, nicht Dirichlet
**Datei:** `src/pareto.py:148–169`. Der Dokstring sagt "Dirichlet-ähnliche Mischung", tatsächlich ist es `random()/sum()` (Uniform-auf-Simplex). Effekt: Mischgewichte sind nicht uniform über das Simplex verteilt, sondern konzentriert in der Mitte. Für die Pareto-Diversität ist das suboptimal.

## N6 — `analyze_team_impact.travel_delta_km` ist ein 500km-Proxy
**Datei:** `src/whatif.py:786–802`. Im Review explizit als Limitation deklariert. Für MLB-Stakeholder ungeeignet — der Aufruf von `compute_team_travel` für das eine Team wäre billig.

## N7 — `_entry_revenue_val(e)` wird im SA pro Move bis zu 4× aufgerufen
**Datei:** `src/generator_optimizer.py:737–742, 763–768`. `_apply_shift_update` und `_revert_shift` rufen jeweils zweimal — einmal für das Delta, einmal für das Caching. Caching in einer lokalen Variable wäre günstiger.

## N8 — `_team_max_streaks._max_run` hat redundante Verzweigung
**Datei:** `src/generator_optimizer.py:234–248`. `if prev is None or d != prev:` umschließt die ganze Logik, dann darunter wieder `if prev is None or d == prev + 1:`. Lesbarer durch frühen Continue auf Doubleheader-Tag.

## N9 — `read_me`-Stil-Konsistenz fehlt zwischen `compute_pareto_bundle` und SA-`_energy_from_state`
**Datei:** `src/generator_optimizer.py:687` vs. `src/pareto_types.py:171`. Das Bundle wird "vollständig" am Ende neu berechnet, was sicher ist — aber das macht die Inkrementalität in der inneren Schleife nur zu einem Approximation. Die Tatsache, dass das *abschließende* `compute_pareto_bundle` korrekt ist, kaschiert M1 (w_off_day skip).

## N10 — `Team.timezone` ohne Validierung gegen TIMEZONE_OFFSET
**Datei:** `src/data_loader.py:81–92`. Wenn `teams.json` eine Timezone einträgt, die nicht im `TIMEZONE_OFFSET` steht (z.B. "America/Mexico_City" für eine Las-Vegas-Verschiebung), wirft `travel_leg` einen `KeyError` — *zur Laufzeit*. Eine Validation im Loader wäre billig.

## N11 — `OAK`-Daten im 2026er Übergangszustand
**Datei:** `data/teams.json` — Athletics werden in Sutter Health Park, West Sacramento, geführt. Für eine MLB-Übergabe sollte abgesprochen sein, ob 2026 = Sacramento oder schon Las Vegas (die Notes deuten an: "Interimsheim 2025–2027 in Sacramento"). Spätestens 2028 muss das nachgeführt werden.

## N12 — `revenue_model.json._calibrated_for_season: 2024` wird für 2026 verwendet
**Datei:** `data/revenue_model.json:3`. 2024-Daten als Modell für 2026 ist eine 2-Jahres-Extrapolation. Inflation, neue Verträge (Apple TV+, neue lokale TV-Deals nach Bally-Sports-Pleite), Stadionrenovierungen verschieben Revenue. Mindestens die Abweichung dokumentieren, idealerweise Modell pro Jahr eichbar machen.

---

# AUFRÄUMEN — Architektonisch

## A1 — `TradeoffProfile` (7-Dim, Sprint 0/1) und `ParetoProfile` (8-Dim, Sprint 2.3b) leben nebeneinander
**Datei:** `src/profiles.py` enthält beide. Die alten benutzen `ai_explainer.py` und `optimizer.py`, die neuen den Hauptpfad. Bei MLB-Übergabe: einen Pfad wählen, anderen entfernen oder klar als legacy markieren.

## A2 — `validation.py` (Sprint 1) vs. `validation_v2.py` (Sprint 2)
`validation_v2.py` importiert aus `validation.py`. Ist V2 eine Erweiterung oder ein Ersatz? Der Loader in `tests/test_infrastructure.py` benutzt V1, `tools/validate_season.py` auch. → siehe M10.

## A3 — `two_phase_repair.py` wird nirgends importiert
Komplette Datei (233 Zeilen) ist Dead Code. Entweder löschen oder mit klarem Hinweis, wann sie aktiviert wird.

## A4 — `tests/test_end_to_end.py` testet die alte Pipeline
…und steht damit im Widerspruch zum eigentlichen Hauptpfad. Bei einer Test-Suite-Aufräumung mitkippen.

## A5 — `pytest-cache-files-df6f65ef/` und `.coverage`-Artefakte im Repo
`.gitignore` enthält sie nicht. Versions-Control-Hygiene.

## A6 — `dashboard/build_dashboard.py` und `build_real_dashboard.py` parallel
Wie auch im `src/`-Code: zwei Generationen, beide live, unklar welche aktuell ist.

---

# Empfehlungen — was vor einer MLB-Übergabe konkret passieren muss

In dieser Reihenfolge, weil sie aufeinander aufbauen:

1. **C1 fixen** (AC-2.1.8-Definition korrigieren, Tests anpassen). Danach alle "AC-2.1.8 erfüllt"-Aussagen erneut verifizieren.
2. **C3 fixen** (Dokstring `_periodic_break_days` + `max_gap`-Default). Wenn C1 sauber umgesetzt wurde, muss die SA-Penalty-Strategie für AC-2.1.8 (neue Definition!) erneut empirisch verifiziert werden.
3. **M10 entscheiden** (welcher Pipeline-Pfad ist der offizielle?). `main.py` und Tests darauf anpassen. Toter Code raus.
4. **C2 fixen** (TV-Slot-Daypart). Mindestens eine Übergangs-Heuristik, die NBC Sunday Night nicht systematisch übersieht.
5. **M3, M4, M5** (What-if-Edge-Cases) — bevor das Dashboard interaktive What-ifs anbietet.
6. **M1** (w_off_day im SA aktivieren oder offiziell aus dem Bundle nehmen).
7. **M2** (DST in Timezone-Offsets).
8. **M9** (Division-Rival-Bonus stacken).

Die Minor- und Aufräum-Punkte können danach in einem zweiten Pass.

---

# Was im Code überzeugt

Es ist wichtig, das auch zu benennen — das hier sind belastbare Stärken, die du behalten solltest:

- **Saubere Sprint-Disziplin:** Jeder Sprint hat ein Review-Dokument, ein Handover, einen klaren Scope. Das ist selten und macht die Architektur nachvollziehbar.
- **Reproduzierbarkeit ist ernst gemeint:** `num_search_workers=1`, deterministische Seeds, dokumentiert. Wenige Repos kümmern sich so explizit darum.
- **Die Sprint-2.3a Column-Generation-Architektur** ist akademisch sauber (Trick/Nemhauser-Ansatz, korrekte RMP-Pricing-Loop mit Big-M=1 zur Vermeidung von Dual-Skalierung). Selbst wenn sie aktuell nicht der Hauptpfad ist — als Backup-Argument bei MLB extrem wertvoll.
- **Datentrennung:** `data/*.json` sauber separiert, Modell-Parameter ohne Code-Änderung swap-bar.
- **Test-Volumen:** ~230+ Tests sind viel und decken die meisten Module ab. Wenn der Mock-Anteil reduziert wird (s. Tests-Abschnitt), ist das eine echte Sicherheitsmarge.
- **What-if-Engine als Konzept:** Trennung zwischen "voller Regenerator" und "schneller Was-wäre-wenn" ist genau, was MLB-Ops haben will.

---

# Anhang — Reproduktions-Snippets

Folgende Snippets reproduzieren die Critical-Befunde am eingecheckten Code:

```python
# C1 — AC-2.1.8 misst falsch (off-day mitten in road trip)
from datetime import date, timedelta
from src.season import Game, Season
from src.player_fatigue import max_consecutive_away_days
base = date(2026, 4, 1)
games = [
    Game(1, base + timedelta(days=0), 'BOS', 'NYY', 'BOS'),
    Game(2, base + timedelta(days=1), 'BOS', 'NYY', 'BOS'),
    Game(3, base + timedelta(days=3), 'BAL', 'NYY', 'BAL'),
    Game(4, base + timedelta(days=4), 'BAL', 'NYY', 'BAL'),
]
s = Season(season=2026, games=games, season_start=base,
           season_end=base + timedelta(days=10))
print(max_consecutive_away_days(s, 'NYY'))   # -> 2  (echte CBA: 5)

# C2 — Sunday Night Baseball wird nie verwendet
from src.tv_slots import TvSlotConfig, _daypart_for_weekday
print(_daypart_for_weekday(6))                # 'day'
print(TvSlotConfig.load().slot_value(6, 'night'))  # 1.6 (nie genutzt)

# C3 — _periodic_break_days mit max_gap=21 (echter Aufruf-Pfad)
from src.generator import _periodic_break_days
print(sorted(_periodic_break_days(100, max_gap=21)))
# -> [20, 41, 62, 83]   Abstand 21 — garantiert AC-2.1.9, NICHT AC-2.1.8
```
