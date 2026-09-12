"""Enkel regelbasert anbefaling for dagens økt, basert på gårsdagens/nattens
data. Ikke en periodisert treningsplan — bare et raskt "bør jeg presse i dag
eller ta det med ro?"-signal fra tallene vi allerede henter.

Merk: statusverdiene fra Garmin ("BALANCED", "OPTIMAL", osv.) er ikke
offisielt dokumentert — reglene her er skrevet mot det vi faktisk har sett
fra egen konto, og bør justeres om du ser andre verdier over tid.
"""

from datetime import date

RACE_DATE = date(2027, 7, 11)  # Ironman 70.3 Jönköping

# Grov periodisering basert på uker igjen til løpet — ikke en detaljert plan,
# bare kontekst for om dagens belastning/øktvalg er rimelig for fasen du er i.
_PHASES = [
    (14, "Taper", "Reduser volum, behold litt intensitet, prioriter hvile og skarphet."),
    (42, "Peak", "Løpsspesifikk intensitet, redusert totalvolum."),
    (98, "Build", "Øk intensitet og volum sammen — nøkkeløkter per idrett."),
    (float("inf"), "Base", "Bygg aerob kapasitet og volum, hold intensiteten lav."),
]


def training_phase(days_left: int) -> tuple[str, str]:
    for max_days, phase, description in _PHASES:
        if days_left <= max_days:
            return phase, description
    return _PHASES[-1][1], _PHASES[-1][2]


_MIN_BASELINE_DAYS = 7  # under dette har vi for lite historikk til å stole på et personlig snitt


def _personal_baseline(values: list[float]) -> tuple[float, float]:
    """(snitt, standardavvik) for en liste med tall."""
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    return mean, variance**0.5


def build_recommendation(
    snapshot: dict,
    sleep_history: list[dict] | None = None,
    health_trends: dict | None = None,
) -> dict:
    """Bygg dagens restitusjonsvurdering.

    `sleep_history` (fra data.get_sleep_trend) og `health_trends` (fra
    data.get_trends) brukes til å kalibrere søvn/HRV/hvilepuls mot DITT EGET
    snitt siste ~30 dager, i stedet for faste terskler som ikke tar hensyn
    til hvor du faktisk ligger. Faller tilbake til faste terskler når det
    ikke finnes nok historikk ennå (< 7 dager).
    """
    flags: list[str] = []
    positives: list[str] = []
    health_trends = health_trends or {}

    # --- Søvn-score: mot eget snitt, fallback til fast terskel -------------
    sovn = snapshot.get("sovn") or {}
    today_score = sovn.get("score")
    score_history = [
        s["score"]
        for s in (sleep_history or [])
        if s.get("score") is not None and s.get("dato") != sovn.get("dato")
    ]
    if today_score and len(score_history) >= _MIN_BASELINE_DAYS:
        mean, std = _personal_baseline(score_history)
        if today_score < mean - max(std, 5):
            flags.append(f"Søvn-score ({today_score}) er under ditt eget snitt siste {len(score_history)} dager ({mean:.0f}).")
        else:
            positives.append(f"Søvn-score ({today_score}) er på linje med ditt eget snitt ({mean:.0f}).")
    elif today_score and today_score < 60:
        flags.append(f"Lav søvn-score ({today_score}) — kroppen har ikke restituert fullt ut.")
    elif today_score:
        positives.append(f"God søvn-score ({today_score}).")

    # --- HRV: Garmins status OG mot eget snitt ------------------------------
    hrv = snapshot.get("hrv") or {}
    hrv_status = hrv.get("status")
    hrv_today = hrv.get("siste_natt_ms")
    hrv_history = [
        v for d, v in (health_trends.get("hrv") or {}).items() if d != hrv.get("dato") and v is not None
    ]
    hrv_mean = None
    hrv_low_vs_baseline = False
    if hrv_today and len(hrv_history) >= _MIN_BASELINE_DAYS:
        hrv_mean, hrv_std = _personal_baseline(hrv_history)
        hrv_low_vs_baseline = hrv_today < hrv_mean - max(hrv_std, 3)

    status_flags_it = bool(hrv_status) and "BALANCED" not in hrv_status
    if status_flags_it or hrv_low_vs_baseline:
        detail = (
            f"HRV-status er '{hrv_status}', ikke balansert"
            if status_flags_it
            else f"HRV ({hrv_today} ms) er under ditt eget snitt ({hrv_mean:.0f} ms)"
        )
        flags.append(f"{detail} — kroppen er under stress.")
    elif hrv_status:
        extra = f" og på linje med ditt eget snitt ({hrv_mean:.0f} ms)" if hrv_mean else ""
        positives.append(f"HRV er i balanse{extra}.")

    # --- Hvilepuls: helt ny signal, kun mot eget snitt ----------------------
    rhr_today = snapshot.get("hvilepuls")
    rhr_history = [
        v for d, v in (health_trends.get("hvilepuls") or {}).items() if d != sovn.get("dato") and v is not None
    ]
    if rhr_today and len(rhr_history) >= _MIN_BASELINE_DAYS:
        rhr_mean, rhr_std = _personal_baseline(rhr_history)
        if rhr_today > rhr_mean + max(rhr_std, 3):
            flags.append(
                f"Hvilepuls ({rhr_today}) er høyere enn ditt eget snitt ({rhr_mean:.0f}) "
                "— mulig tegn på at kroppen ikke er ferdig restituert."
            )
        else:
            positives.append(f"Hvilepuls ({rhr_today}) er på linje med ditt eget snitt ({rhr_mean:.0f}).")

    # --- Treningsbelastning: allerede et selv-relativt mål ------------------
    trening = snapshot.get("trening") or {}
    ratio = trening.get("belastningsforhold")
    load_status = trening.get("belastning_status")
    if ratio is not None and ratio > 1.5:
        flags.append(f"Akutt/kronisk belastningsforhold er høyt ({ratio}) — skaderisiko øker.")
    elif load_status and load_status != "OPTIMAL":
        flags.append(f"Belastningsstatus er '{load_status}', ikke optimal.")
    elif ratio is not None:
        positives.append(f"Belastningsforhold ser greit ut ({ratio}).")

    bb = snapshot.get("body_battery") or {}
    if bb.get("naa") is not None and bb["naa"] < 30:
        flags.append(f"Body Battery er lav ({bb['naa']}/100).")

    if len(flags) >= 2:
        verdict = "Hviledag eller lett økt"
    elif len(flags) == 1:
        verdict = "Ta det litt roligere i dag"
    elif ratio is not None and ratio < 0.8:
        verdict = "Klar for en hardøkt"
        positives.append("Belastningen er lav relativt til kapasitet — rom for å presse på.")
    else:
        verdict = "Normal treningsdag"

    return {"verdict": verdict, "flags": flags, "positives": positives}


# --- Anbefalt økt per idrett ------------------------------------------------

_LONG_SESSION_THRESHOLD = {
    "Løping": ("distanse_km", 10),
    "Sykling": ("distanse_km", 40),
    "Svømming": ("distanse_km", 2),
}

_SESSION_TEMPLATES = {
    "Løping": {
        "hvile": ("Hvile eller svært lett jogg", "20 min i snakketempo, eller ta fri."),
        "rolig": ("Rolig løpetur", "30–45 min i sone 2, lav intensitet."),
        "langtur": ("Langtur", "90+ min i rolig, jevnt tempo — bygg mot 70.3-distansen."),
        "intervall": ("Intervall-/terskeløkt", "F.eks. 4×8 min i terskeltempo med jogg imellom."),
        "normal": ("Moderat løpetur", "40–50 min i jevnt, moderat tempo."),
    },
    "Sykling": {
        "hvile": ("Hvile eller svært rolig tur", "30 min, veldig lav intensitet, eller ta fri."),
        "rolig": ("Rolig sykkeltur", "45–60 min, lav intensitet."),
        "langtur": ("Langtur på sykkel", "2+ timer i jevnt, rolig tempo."),
        "intervall": ("Intervalløkt", "F.eks. 4×10 min i terskelwatt/-puls."),
        "normal": ("Moderat sykkeltur", "60–90 min, jevnt tempo."),
    },
    "Svømming": {
        "hvile": ("Hvile eller teknikkøkt", "Kort og rolig, fokus på teknikk, eller ta fri."),
        "rolig": ("Rolig svømmeøkt", "30 min, fokus på teknikk og rytme."),
        "langtur": ("Lengre svømmeøkt", "45–60 min sammenhengende, bygg utholdenhet."),
        "intervall": ("Intervaller i bassenget", "F.eks. 10×100m med kort pause."),
        "normal": ("Moderat svømmeøkt", "30–40 min, jevnt tempo."),
    },
}


def _adaptive_long_threshold(sessions: list[dict], sport: str) -> float:
    """70 % av din egen lengste økt siste ~8 uker — skalerer med formen din,
    i stedet for et fast tall som blir feil både for en nybegynner og en
    erfaren utøver. Faller tilbake til et fast standardtall uten nok historikk.
    """
    metric, default_min = _LONG_SESSION_THRESHOLD[sport]
    # Sorter eksplisitt — vi skal ikke stole på hvilken rekkefølge Garmin-APIet
    # returnerer aktiviteter i.
    recent_sorted = sorted((s for s in sessions if s.get("dato")), key=lambda s: s["dato"], reverse=True)
    recent = [v for s in recent_sorted[:16] if (v := s.get(metric) or 0) > 0]  # ~8 uker typisk frekvens
    if len(recent) < 3:
        return default_min
    return max(sorted(recent)[-1] * 0.7, default_min * 0.5)


def _has_long_session_this_week(sessions: list[dict], sport: str) -> bool:
    from data import _week_key  # samme ukenøkkel som resten av dashbordet bruker

    metric, _ = _LONG_SESSION_THRESHOLD[sport]
    threshold = _adaptive_long_threshold(sessions, sport)
    this_week = _week_key({"dato": date.today().isoformat()})
    return any(_week_key(s) == this_week and (s.get(metric) or 0) >= threshold for s in sessions)


def recommend_session(sport: str, readiness_verdict: str, phase: str, sessions: list[dict]) -> dict:
    """Anbefal type økt for en gitt idrett: bruker samme restitusjonsverdikt som
    forsiden, treningsfasen, og om en langtur allerede er gjort denne uken.

    Rekkefølgen på reglene er bevisst: restitusjonssignaler og taper-fasen
    overstyrer alltid, uansett hvor «skyldig» du er en langtur eller hardøkt.
    """
    if readiness_verdict == "Hviledag eller lett økt":
        session_type = "hvile"
        reasoning = ["Restitusjonssignalene i dag tilsier hvile eller noe svært lett."]
    elif readiness_verdict == "Ta det litt roligere i dag":
        session_type = "rolig"
        reasoning = ["Restitusjonssignalene i dag tilsier en rolig økt, ikke noe hardt."]
    elif phase == "Taper":
        session_type = "rolig"
        reasoning = ["Du er i taper-fasen — korte, rolige økter uansett følelse i dag."]
    elif not _has_long_session_this_week(sessions, sport):
        session_type = "langtur"
        reasoning = ["Ingen langtur i denne idretten denne uken ennå, og restitusjonen er god."]
    elif readiness_verdict == "Klar for en hardøkt" and phase in ("Build", "Peak"):
        session_type = "intervall"
        reasoning = [f"God restitusjon og du er i {phase}-fasen — rom for en hardøkt."]
    elif phase == "Base":
        session_type = "rolig"
        reasoning = ["Base-fasen prioriterer aerob kapasitet fremfor intensitet."]
    else:
        session_type = "normal"
        reasoning = ["Ingen spesielle flagg — en vanlig, moderat økt passer fint."]

    title, description = _SESSION_TEMPLATES[sport][session_type]
    return {"tittel": title, "beskrivelse": description, "begrunnelse": reasoning}
