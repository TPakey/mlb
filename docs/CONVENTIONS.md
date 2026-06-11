# Code-Konventionen

**Stand:** 2026-05-28 (Sprint A-5, Audit A16)

Dieses Dokument hält die Konventionen fest, die im Repo gelten — historisch
gewachsen, hier explizit gemacht.

## Sprache

| Wo | Sprache | Begründung |
|---|---|---|
| **Identifier** (Klassen, Funktionen, Variablen) | **Englisch** | Internationaler Standard; Tools/Suchen funktionieren erwartet. |
| **Inline-Kommentare** | **Deutsch** | Stakeholder-Reviews (intern + MLB) lesen primär Deutsch. |
| **Dokstrings (Module, Klassen, öffentliche Funktionen)** | **Deutsch** | Wie Inline-Kommentare. Stakeholder-lesbar. |
| **Test-Namen + -Dokstrings** | **Deutsch** | Konsistent mit der Doku. |
| **Repo-Docs (`docs/*.md`)** | **Deutsch** | Stakeholder-Sprache. |
| **Audit-/Sprint-Bezeichner in Kommentaren** | Beispiel: `# Audit A11 (Sprint A-2):` | Audit-Trail bleibt nachvollziehbar. |

Neue Beiträge halten sich an diese Konvention. Bestehende Inkonsistenzen
werden bei Berührung mit-korrigiert (Boy-Scout-Rule), nicht in eigenen Sprints
gejagt.

## Imports

- **Modulebene** für alles, was im Hot-Path benutzt wird.
- **Lazy (in der Funktion)** nur dann, wenn:
  - Es eine zirkuläre Abhängigkeit gibt (dann sollte das aber refactored werden — siehe A15/`src/timezones.py`).
  - Es ein optionales Feature ist (Plot-Libs, etc.).
  - Die Initialisierung teuer ist (`.load()`-Aufrufe für JSON-Konfigurationen).

## Logging

- `print()` ist verboten in `src/` (Audit A17). Stattdessen
  `logger = logging.getLogger("mlb.<modul>")` am Modul-Anfang.
- CLI-Skripte (`tools/*`, `src/main.py`) konfigurieren `logging.basicConfig`
  einmal, der Rest des Codes nutzt nur `getLogger`.
- Log-Level über die Umgebungsvariable `MLB_LOG_LEVEL` (Default `INFO`).

## Tests

- **Marker:** `slow`, `integration`, `property`. CI trennt fast/slow.
- **Gemeinsame Helfer** liegen in `tests/conftest.py` (`make_game`,
  `make_mini_season`); neue Tests nutzen die.
- **xfail** ist ein legitimes Werkzeug für dokumentierte offene Limitationen
  — IMMER mit `reason=` und Verweis auf das passende Doc.

## Architektur-Layer

```
data/ ──→ data_loader, timezones, datasources/
             ↓
         season, distance, profiles, tv_slots, revenue, player_fatigue,
         matchup_extractor, event_conflicts, travel
             ↓
         generator → generator_optimizer
             ↓
         pareto, pareto_types, whatif, disruption, repair_*
             ↓
         main (CLI), tools/, dashboard/

         src/legacy/         (deprecated Sprint-0/1-Pfad, importiert nur Basis-Module via `..`)
```

Die rechte Spalte importiert NIE die linke. `src/legacy/` ist isoliert.
