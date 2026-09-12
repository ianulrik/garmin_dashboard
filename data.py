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

    return {
        "sovn": {
            "dato": sleep_day,
            "total_min": round((dto.get("sleepTimeSeconds") or 0) / 60, 1),
            "dyp_min": round((dto.get("deepSleepSeconds") or 0) / 60, 1),
            "score": sleep_overall.get("value"),
            "kvalitet": sleep_overall.get("qualifierKey"),
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
def get_recent_activities(limit: int = 8) -> list[dict]:
    client = _client()
    activities = client.get_activities(0, limit)
    return [
        {
            "navn": a.get("activityName"),
            "type": (a.get("activityType") or {}).get("typeKey"),
            "dato": a.get("startTimeLocal"),
            "varighet_min": round(a.get("duration", 0) / 60, 1),
            "distanse_km": round(a["distance"] / 1000, 2) if a.get("distance") else None,
        }
        for a in activities
    ]
