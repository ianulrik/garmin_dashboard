"""Henter og former Garmin-data til dashbordet.

Streamlit kjører HELE skriptet på nytt for hver interaksjon (klikk, slider,
etc.) — uten caching ville det trigget nye Garmin-API-kall konstant, med fare
for GarminConnectTooManyRequestsError. @st.cache_data(ttl=...) cacher
resultatet i minnet i et gitt tidsrom, så data faktisk kun hentes på nytt
periodisk (matcher "periodisk oppdaterte data", ikke sanntid).
"""

from datetime import date, timedelta

import streamlit as st

from garmin_client import get_client

REFRESH_SECONDS = 600  # 10 min


@st.cache_resource
def _client():
    return get_client()


def _latest_available_day(fetch, max_days_back: int = 3) -> tuple[str, dict]:
    """Prøv i dag, og gå bakover i tid til vi finner en dag med data.

    Søvn/HRV for "i natt" er ofte ikke synkronisert ennå tidlig på morgenen.
    """
    for offset in range(max_days_back):
        day = (date.today() - timedelta(days=offset)).isoformat()
        raw = fetch(day)
        if raw:
            return day, raw
    return date.today().isoformat(), {}


@st.cache_data(ttl=REFRESH_SECONDS)
def get_health_snapshot() -> dict:
    client = _client()

    sleep_day, sleep_raw = _latest_available_day(client.get_sleep_data)
    dto = sleep_raw.get("dailySleepDTO") or {}
    sleep_overall = (dto.get("sleepScores") or {}).get("overall") or {}

    hrv_day, hrv_raw = _latest_available_day(client.get_hrv_data)
    hrv_summary = hrv_raw.get("hrvSummary") or {}

    today = date.today().isoformat()
    training_raw = client.get_training_status(today) or {}
    latest = (training_raw.get("mostRecentTrainingStatus") or {}).get("latestTrainingStatusData") or {}
    device_data = next(iter(latest.values()), {}) if latest else {}
    acute = device_data.get("acuteTrainingLoadDTO") or {}
    vo2max = ((training_raw.get("mostRecentVO2Max") or {}).get("generic") or {}).get("vo2MaxValue")

    rhr_rows = client.get_rhr_daily(today, today) or []
    rhr = rhr_rows[0].get("value") if rhr_rows else None

    bb_rows = client.get_body_battery(today, today) or []
    bb = bb_rows[0] if bb_rows else {}
    bb_values = bb.get("bodyBatteryValuesArray") or []
    bb_current = bb_values[-1][1] if bb_values else None

    next_need = dto.get("nextSleepNeed") or {}

    load_balance_map = (training_raw.get("mostRecentTrainingLoadBalance") or {}).get(
        "metricsTrainingLoadBalanceDTOMap"
    ) or {}
    load_balance = next(iter(load_balance_map.values()), {}) if load_balance_map else {}

    return {
        "sovn": {
            "dato": sleep_day,
            "total_min": round((dto.get("sleepTimeSeconds") or 0) / 60, 1),
            "dyp_min": round((dto.get("deepSleepSeconds") or 0) / 60, 1),
            "lett_min": round((dto.get("lightSleepSeconds") or 0) / 60, 1),
            "rem_min": round((dto.get("remSleepSeconds") or 0) / 60, 1),
            "vaken_min": round((dto.get("awakeSleepSeconds") or 0) / 60, 1),
            "score": sleep_overall.get("value"),
            "kvalitet": sleep_overall.get("qualifierKey"),
            "snitt_stress": dto.get("avgSleepStress"),
            "antall_oppvakninger": dto.get("awakeCount"),
            # Garmins egen søvnbehov-modell for KOMMENDE natt, justert for bl.a.
            # dagens treningsbelastning — ikke noe vi regner ut selv.
            "anbefalt_naa_min": next_need.get("baseline"),
            "anbefalt_justert_min": next_need.get("actual"),
            "anbefaling_retning": next_need.get("feedback"),
        },
        "hrv": {
            "dato": hrv_day,
            "siste_natt_ms": hrv_summary.get("lastNightAvg"),
            "ukentlig_ms": hrv_summary.get("weeklyAvg"),
            "status": hrv_summary.get("status"),
        },
        "hvilepuls": rhr,
        "body_battery": {
            "naa": bb_current,
            "ladet": bb.get("charged"),
            "tappet": bb.get("drained"),
        },
        "trening": {
            "status": device_data.get("trainingStatusFeedbackPhrase"),
            "akutt_belastning": acute.get("dailyTrainingLoadAcute"),
            "kronisk_belastning": acute.get("dailyTrainingLoadChronic"),
            "belastningsforhold": acute.get("dailyAcuteChronicWorkloadRatio"),
            "belastning_status": acute.get("acwrStatus"),
            "vo2max": vo2max,
            # Månedlig belastningsfordeling: aktuell vs. Garmins anbefalte
            # målsone, "gratis" fra samme kall vi allerede gjør over.
            "manedlig_balanse": {
                "aerob_lav": load_balance.get("monthlyLoadAerobicLow"),
                "aerob_lav_mal": (
                    load_balance.get("monthlyLoadAerobicLowTargetMin"),
                    load_balance.get("monthlyLoadAerobicLowTargetMax"),
                ),
                "aerob_hoy": load_balance.get("monthlyLoadAerobicHigh"),
                "aerob_hoy_mal": (
                    load_balance.get("monthlyLoadAerobicHighTargetMin"),
                    load_balance.get("monthlyLoadAerobicHighTargetMax"),
                ),
                "anaerob": load_balance.get("monthlyLoadAnaerobic"),
                "anaerob_mal": (
                    load_balance.get("monthlyLoadAnaerobicTargetMin"),
                    load_balance.get("monthlyLoadAnaerobicTargetMax"),
                ),
                "feedback": load_balance.get("trainingBalanceFeedbackPhrase"),
            },
        },
    }


@st.cache_data(ttl=REFRESH_SECONDS)
def get_trends(days: int = 14) -> dict:
    client = _client()
    end = date.today()
    start = end - timedelta(days=days - 1)
    start_s, end_s = start.isoformat(), end.isoformat()

    rhr_rows = client.get_rhr_daily(start_s, end_s) or []
    hrv_rows = (client.get_hrv_data_range(start_s, end_s) or {}).get("hrvSummaries") or []
    bb_rows = client.get_body_battery(start_s, end_s) or []

    return {
        "hvilepuls": {r["calendarDate"]: r.get("value") for r in rhr_rows},
        "hrv": {r["calendarDate"]: r.get("lastNightAvg") for r in hrv_rows},
        "body_battery_ladet": {r["date"]: r.get("charged") for r in bb_rows},
    }


@st.cache_data(ttl=REFRESH_SECONDS)
def get_sleep_trend(days: int = 14) -> list[dict]:
    client = _client()
    end = date.today()
    start = end - timedelta(days=days - 1)
    rows = client.get_sleep_daily(start.isoformat(), end.isoformat()) or []
    return [
        {
            "dato": r["calendarDate"],
            "timer": round((r.get("values") or {}).get("totalSleepTimeInSeconds", 0) / 3600, 2),
            "score": (r.get("values") or {}).get("sleepScore"),
            "kvalitet": (r.get("values") or {}).get("sleepScoreQuality"),
        }
        for r in rows
    ]


# Garmin sin egen type-filtrering (activitytype-parameteren) matcher ikke
# nødvendigvis alle varianter du faktisk bruker (f.eks. "trail_running" vs
# "running"), så vi henter alt rått i perioden og kategoriserer selv på
# nøkkelord i typeKey — mer robust og lettere å justere enn å stole på
# Garmins egen filter-taksonomi.
_SPORT_KEYWORDS = {
    "Løping": ["running"],
    "Sykling": ["cycling", "biking", "bike", "ride"],
    "Svømming": ["swimming"],
    "Styrke": ["strength"],
}


def _categorize(type_key: str | None) -> str:
    type_key = (type_key or "").lower()
    for sport, keywords in _SPORT_KEYWORDS.items():
        if any(kw in type_key for kw in keywords):
            return sport
    return "Annet"


@st.cache_data(ttl=REFRESH_SECONDS)
def get_activity_history(days: int = 90) -> dict[str, list[dict]]:
    """Hent økter siste `days` dager, gruppert per idrett."""
    client = _client()
    end = date.today()
    start = end - timedelta(days=days - 1)
    activities = client.get_activities_by_date(start.isoformat(), end.isoformat()) or []

    by_sport: dict[str, list[dict]] = {sport: [] for sport in _SPORT_KEYWORDS}
    by_sport["Annet"] = []

    for a in activities:
        sport = _categorize((a.get("activityType") or {}).get("typeKey"))
        speed = a.get("averageSpeed") or 0  # m/s
        session = {
            "dato": a.get("startTimeLocal"),
            "navn": a.get("activityName"),
            "varighet_min": round(a.get("duration", 0) / 60, 1),
            "distanse_km": round(a["distance"] / 1000, 2) if a.get("distance") else None,
            "tempo_min_per_km": round(1000 / (speed * 60), 2) if speed > 0 else None,
            "fart_kmh": round(speed * 3.6, 1) if speed > 0 else None,
            "snitt_puls": a.get("averageHR"),
            "maks_puls": a.get("maxHR"),
            "kadens": a.get("averageRunningCadenceInStepsPerMinute"),
            "hoydemeter": a.get("elevationGain"),
            "treningseffekt": a.get("trainingEffectLabel"),
            "aerob_effekt": a.get("aerobicTrainingEffect"),
            "anaerob_effekt": a.get("anaerobicTrainingEffect"),
            "puls_sone_min": {
                z: round((a.get(f"hrTimeInZone_{z}") or 0) / 60, 1) for z in range(1, 6)
            },
            "treningsbelastning": a.get("activityTrainingLoad"),
        }
        by_sport[sport].append(session)

    return by_sport


@st.cache_data(ttl=REFRESH_SECONDS)
def get_vo2max_trend(months: int = 6) -> dict[str, dict[str, float]]:
    """VO2maks-utvikling siste `months` måneder, løping og sykling separat.

    Sykling er ofte tom (krever effektmåler/-data) — vises kun om Garmin
    faktisk har beregnet det for kontoen din.
    """
    client = _client()
    end = date.today()
    start = end - timedelta(days=months * 30)
    rows = client.get_max_metrics_range(start.isoformat(), end.isoformat()) or []

    running: dict[str, float] = {}
    cycling: dict[str, float] = {}
    for r in rows:
        generic = r.get("generic") or {}
        if generic.get("calendarDate") and generic.get("vo2MaxPreciseValue") is not None:
            running[generic["calendarDate"]] = generic["vo2MaxPreciseValue"]
        cyc = r.get("cycling") or {}
        if cyc.get("calendarDate") and cyc.get("vo2MaxPreciseValue") is not None:
            cycling[cyc["calendarDate"]] = cyc["vo2MaxPreciseValue"]

    return {"loping": dict(sorted(running.items())), "sykling": dict(sorted(cycling.items()))}


def _week_key(session: dict) -> str | None:
    if not session.get("dato"):
        return None
    d = date.fromisoformat(session["dato"][:10])
    return f"{d.isocalendar().year}-U{d.isocalendar().week:02d}"


def weekly_volume(sessions: list[dict], metric: str = "distanse_km") -> dict[str, float]:
    """Summer `metric` per ISO-uke, for en utviklings-graf per idrett."""
    from collections import defaultdict

    totals: dict[str, float] = defaultdict(float)
    for s in sessions:
        week_key = _week_key(s)
        if week_key:
            totals[week_key] += s.get(metric) or 0
    return dict(sorted(totals.items()))


def weekly_longest(sessions: list[dict], metric: str = "distanse_km") -> dict[str, float]:
    """Lengste økt (på `metric`) per ISO-uke — langtur-progresjon."""
    from collections import defaultdict

    longest: dict[str, float] = defaultdict(float)
    for s in sessions:
        week_key = _week_key(s)
        value = s.get(metric) or 0
        if week_key and value > longest[week_key]:
            longest[week_key] = value
    return dict(sorted(longest.items()))


def hr_zone_distribution(sessions: list[dict]) -> dict[int, float]:
    """Summer minutter i hver pulssone over gitte økter."""
    totals = dict.fromkeys(range(1, 6), 0.0)
    for s in sessions:
        for zone, minutes in (s.get("puls_sone_min") or {}).items():
            totals[zone] += minutes
    return totals


def get_weekly_load_trend(days: int = 90) -> dict[str, float]:
    """Ukentlig sum av Garmins per-økt treningsbelastning, alle idretter samlet.

    Viser om oppbyggingen mot 70.3 er jevn eller hoppete (brå økninger øker
    skaderisiko) — i motsetning til dagens akutt/kronisk-forhold, som bare
    viser ett øyeblikksbilde.
    """
    history = get_activity_history(days=days)
    all_sessions = [s for sessions in history.values() for s in sessions]
    return weekly_volume(all_sessions, metric="treningsbelastning")


def get_weekly_training_balance(days: int = 84) -> dict[str, dict[str, float]]:
    """Ukentlige timer per idrett (styrke/løping/sykling/svømming), for å se
    balansen mellom grenene — ikke bare hver gren isolert."""
    history = get_activity_history(days=days)
    balance: dict[str, dict[str, float]] = {}
    for sport in _SPORT_KEYWORDS:
        weekly_min = weekly_volume(history.get(sport, []), metric="varighet_min")
        balance[sport] = {week: round(minutes / 60, 2) for week, minutes in weekly_min.items()}
    return balance


def _format_race_time(seconds: int | None) -> str | None:
    if not seconds:
        return None
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


@st.cache_data(ttl=REFRESH_SECONDS)
def get_race_predictions() -> dict[str, str | None]:
    """Garmins estimerte løpstider basert på nåværende form."""
    client = _client()
    raw = client.get_race_predictions() or {}
    return {
        "5 km": _format_race_time(raw.get("time5K")),
        "10 km": _format_race_time(raw.get("time10K")),
        "Halvmaraton": _format_race_time(raw.get("timeHalfMarathon")),
        "Maraton": _format_race_time(raw.get("timeMarathon")),
    }
