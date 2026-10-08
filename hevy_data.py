"""Henter styrkeøkter fra Hevy via hevy_mcp-pakken (samme klient, innlogging og
utregninger som Hevy-MCP-serveren Claude bruker).

Styrke hentes herfra i stedet for fra Garmin fordi Garmin bare vet at en
styrkeøkt fant sted — Hevy har øvelser, sett, kg og reps.
"""

from datetime import date, timedelta

import streamlit as st
from hevy_mcp.client import HevyClient
from hevy_mcp.tools.fmt import fmt_workout, normalize_workout

from data import REFRESH_SECONDS

MUSCLE_NAMES = {
    "chest": "Bryst",
    "lats": "Lats",
    "upper_back": "Øvre rygg",
    "lower_back": "Korsrygg",
    "traps": "Trapes",
    "shoulders": "Skuldre",
    "biceps": "Biceps",
    "triceps": "Triceps",
    "forearms": "Underarmer",
    "abdominals": "Mage",
    "quadriceps": "Forside lår",
    "hamstrings": "Bakside lår",
    "glutes": "Sete",
    "calves": "Legger",
    "adductors": "Adduktorer",
    "abductors": "Abduktorer",
    "neck": "Nakke",
    "cardio": "Kondisjon",
    "full_body": "Hele kroppen",
    "other": "Annet",
}


@st.cache_resource
def _client() -> HevyClient:
    return HevyClient()


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner="Henter økter fra Hevy …")
def get_strength_workouts() -> list[dict]:
    """Alle Hevy-økter, nyeste først, med sett og oppsummering per øvelse."""
    return [fmt_workout(normalize_workout(w), detailed=True) for w in _client().all_workouts()]


def in_window(workouts: list[dict], start_days_ago: int, end_days_ago: int = 0) -> list[dict]:
    """Økter med dato i [i dag - start_days_ago + 1, i dag - end_days_ago]."""
    today = date.today()
    first = (today - timedelta(days=start_days_ago - 1)).isoformat()
    last = (today - timedelta(days=end_days_ago)).isoformat()
    return [w for w in workouts if first <= (w.get("dato") or "") <= last]


def exercise_sessions(workouts: list[dict], exercise_id: str) -> list[dict]:
    """Hver gang en øvelse er gjort (eldst først), med dato og øktnavn."""
    rows = []
    for w in workouts:
        for ex in w["ovelser"]:
            if ex.get("ovelse_id") == exercise_id:
                rows.append({"dato": w["dato"], "okt": w.get("tittel"), **ex})
    return sorted(rows, key=lambda r: r["dato"])


def format_sets(sets: list[dict]) -> str:
    """'80×5, 80×5, 70×8 (d)' — arbeidssett; oppvarming utelates."""
    parts = []
    for s in sets:
        if s.get("type") == "oppvarming":
            continue
        if s.get("kg") is not None and s.get("reps") is not None:
            text = f"{s['kg']:g}×{s['reps']}"
        elif s.get("reps") is not None:
            text = f"{s['reps']} reps"
        elif s.get("sek") is not None:
            text = f"{s['sek']} s"
        else:
            continue
        if s.get("type") == "dropsett":
            text += " (d)"
        elif s.get("type") == "til_failure":
            text += " (f)"
        if s.get("pr"):
            text += " 🏆"
        parts.append(text)
    return ", ".join(parts)
