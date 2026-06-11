"""City-Security- & Risiko-Briefing (Scheduler-Ops, MLB-Niveau).

Ein professionelles Travel-Security-Briefing, wie es MLB-Club-Security / League
Security für jede Gast-Stadt erwartet — **fakten-basiert, severity-bewertet,
saison-/datums-abhängig**, nicht alarmistisch und nicht „Kindergarten".

Quellen: `data/city_ops_profiles.json` (regionale Klimatologie — verifizierbar;
Principal Level-I Trauma Center — öffentlicher Record; Metro-Verkehrslage).
Game-Day-spezifische Lage (aktuelle Bedrohungseinstufung, On-Call-EMS-Routing,
VIP-/Protest-Lage) ist bewusst als **Liaison-Feld** ausgewiesen — solche Daten
kommen am Spieltag vom lokalen Law-Enforcement-/EMS-Kontakt, nicht aus einem
statischen Modell. Das Briefing liefert die belastbare Grundstruktur + alle
verifizierbaren Fakten und markiert klar, was vor Ort zu bestätigen ist.

Kategorien (MLB-Ops-Standard):
1. Wetter & Naturgefahren (severity, Saison, Dach-Mitigation)
2. Medizinische Bereitschaft (Trauma-Center, On-Site-EMS, Routing)
3. Boden-Transport-Risiko (Stau → Planbarkeit, empfohlener Puffer)
4. Venue- & Crowd-Security (Dach/offen, Posture; High-Profile-Flag im Dossier)
5. Notfall-Framework (Evakuierung, Comms, Liaison-Kontakte als Felder)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Deutsche Monats-Abkürzungen → Nummer (für die Saison-Aktiv-Prüfung)
_MONTHS = {"jan": 1, "feb": 2, "mär": 3, "mar": 3, "apr": 4, "mai": 5, "jun": 6,
           "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dez": 12}


def _parse_months(spec: str) -> set:
    """Parst Strings wie 'Jun–Nov', 'Apr–Mai, Sep', 'ganzjährig' → Monats-Set."""
    spec = spec.strip().lower()
    if "ganzj" in spec:
        return set(range(1, 13))
    out: set = set()
    for tok in spec.replace("—", "–").split(","):
        tok = tok.strip()
        if "–" in tok:
            a, b = [x.strip()[:3] for x in tok.split("–")]
            ma, mb = _MONTHS.get(a), _MONTHS.get(b)
            if ma and mb:
                m = ma
                while True:
                    out.add(m)
                    if m == mb:
                        break
                    m = m % 12 + 1
        else:
            mm = _MONTHS.get(tok[:3])
            if mm:
                out.add(mm)
    return out


def load_ops_profiles(path: Optional[Path] = None) -> Dict[str, dict]:
    path = path or (DATA_DIR / "city_ops_profiles.json")
    return json.loads(Path(path).read_text(encoding="utf-8"))["profiles"]


_RISK_WORD = {0: "Minimal", 1: "Niedrig", 2: "Niedrig", 3: "Erhöht",
              4: "Hoch", 5: "Kritisch"}


@dataclass(frozen=True)
class SecurityBriefing:
    team_id: str
    city: str
    stadium: str
    month: Optional[int]
    active_hazards: List[dict]        # in der Saison/Monat relevante Klimagefahren
    all_hazards: List[dict]
    trauma_center: Optional[str]
    transport_reliability: float      # 0..1 (aus Congestion/Redundanz)
    transport_note: str
    roof: str
    overall_severity: int             # 0..5
    recommended_posture: str

    @property
    def risk_level(self) -> str:
        return _RISK_WORD[self.overall_severity]

    def to_dict(self) -> dict:
        return {
            "team_id": self.team_id, "city": self.city, "stadium": self.stadium,
            "month": self.month, "risk_level": self.risk_level,
            "overall_severity": self.overall_severity,
            "active_hazards": self.active_hazards,
            "trauma_center": self.trauma_center,
            "transport_reliability": round(self.transport_reliability, 2),
            "roof": self.roof,
            "recommended_posture": self.recommended_posture,
        }


def _transport_reliability(congestion: float, redundancy: int) -> float:
    base = 1.10 - 0.42 * (congestion - 1.0) + 0.05 * max(0, redundancy - 1)
    return max(0.15, min(0.99, base))


def build_security_briefing(team_id: str, *, month: Optional[int] = None,
                            profiles: Optional[Dict[str, dict]] = None) -> SecurityBriefing:
    """Erzeugt das Security-Briefing für die Gast-Stadt von ``team_id``.

    ``month`` (1–12) macht das Briefing saison-bewusst: nur die in diesem Monat
    aktiven Klimagefahren fließen in die Gesamt-Severity ein. Ohne Monat zählt
    das ganzjährige Maximum.
    """
    profiles = profiles or load_ops_profiles()
    p = profiles[team_id]
    hazards = p.get("climate_hazards", [])

    if month is not None:
        active = [h for h in hazards if month in _parse_months(h["months"])]
    else:
        active = list(hazards)

    max_hazard_sev = max((h["severity"] for h in active), default=0)

    rel = _transport_reliability(p.get("congestion", 1.4), p.get("route_redundancy", 2))
    # Transport trägt zur Gesamt-Severity bei: schlechte Planbarkeit = +1.
    transport_sev = 3 if rel < 0.55 else (2 if rel < 0.75 else 1)
    overall = min(5, max(max_hazard_sev, transport_sev))

    roof = p.get("roof", "open")
    roof_note = {
        "dome": "Feste Überdachung — Wetter-Spielausfälle praktisch ausgeschlossen.",
        "retractable": "Schließbares Dach — Hitze/Regen/Rauch mitigierbar (Dach-Entscheidung früh treffen).",
        "open": "Offenes Stadion — volle Wetterexposition; Verzögerungs-/Makeup-Protokoll bereithalten.",
    }.get(roof, "")

    posture_bits = []
    if overall >= 4:
        posture_bits.append("Erhöhte Wachsamkeit: Wetter-/Lage-Monitoring im 6-h-Takt, Makeup-Optionen vorhalten.")
    elif overall == 3:
        posture_bits.append("Standard-plus: tägliches Wetter-/Verkehrs-Briefing, Zeitpuffer einplanen.")
    else:
        posture_bits.append("Standard-Posture ausreichend.")
    if rel < 0.6:
        posture_bits.append(f"Transfer-Puffer großzügig (Planbarkeit {rel:.0%}); Polizei-Eskorte für Gameday-Transfer prüfen.")
    if roof == "open" and max_hazard_sev >= 3:
        posture_bits.append("Offenes Stadion bei erhöhter Wettergefahr — Blitz-/Sturm-Abbruchkette mit Venue-Ops abstimmen.")

    return SecurityBriefing(
        team_id=team_id, city=p.get("city", ""), stadium=p.get("stadium", ""),
        month=month, active_hazards=active, all_hazards=hazards,
        trauma_center=(p.get("trauma_center") or {}).get("name"),
        transport_reliability=rel, transport_note=roof_note,
        roof=roof, overall_severity=overall,
        recommended_posture=" ".join(posture_bits),
    )


def briefing_to_markdown(b: SecurityBriefing) -> str:
    L: List[str] = []
    L.append(f"### Security- & Risiko-Briefing — {b.city} ({b.stadium})")
    L.append(f"**Gesamt-Risikostufe: {b.risk_level}** (Severity {b.overall_severity}/5)"
             + (f" · Monat {b.month}" if b.month else ""))
    L.append("")
    # 1. Wetter & Naturgefahren
    L.append("**1. Wetter & Naturgefahren**")
    if b.active_hazards:
        for h in sorted(b.active_hazards, key=lambda x: -x["severity"]):
            L.append(f"- [{h['severity']}/5] {h['hazard']} ({h['months']}): {h['note']}")
    else:
        L.append("- Keine saisonal aktiven Naturgefahren erfasst.")
    if b.transport_note:
        L.append(f"- Venue: {b.transport_note}")
    L.append("")
    # 2. Medizinische Bereitschaft
    L.append("**2. Medizinische Bereitschaft**")
    L.append(f"- Principal Level-I Trauma-Center: {b.trauma_center or '— (mit lokalem EMS-Liaison bestätigen)'}.")
    L.append("- On-Site: MLB-Standard sieht Game-Day-EMS + Teamärzte am Venue vor; "
             "On-Call-Klinik-Routing mit lokalem EMS-Liaison final bestätigen.")
    L.append("")
    # 3. Boden-Transport
    L.append("**3. Boden-Transport-Risiko**")
    L.append(f"- Planbarkeit der Transfers: {b.transport_reliability:.0%} "
             f"({'unzuverlässig — Puffer/Eskorte' if b.transport_reliability < 0.6 else 'solide' if b.transport_reliability < 0.85 else 'gut'}).")
    L.append("")
    # 4. Venue/Crowd
    L.append("**4. Venue- & Crowd-Security**")
    L.append(f"- Stadiontyp: {b.roof}. High-Profile-Begegnungen (Rivalität/Feiertag) "
             "erhöhen Crowd-Posture — siehe Trip-Dossier-Kontext.")
    L.append("")
    # 5. Notfall-Framework
    L.append("**5. Notfall-Framework** (vor Ort zu finalisieren)")
    L.append("- Evakuierungsrouten Venue↔Hotel, Sammelpunkte, redundante Comms.")
    L.append("- Liaison-Kontakte: lokales PD, Venue-Security-Lead, EMS, Club-Security. [Felder]")
    L.append("")
    L.append(f"**Empfohlene Posture:** {b.recommended_posture}")
    return "\n".join(L)
