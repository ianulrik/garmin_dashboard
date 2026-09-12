import functools
from datetime import date

import pandas as pd
import streamlit as st
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from data import get_activity_history, get_health_snapshot, get_sleep_trend, get_trends, weekly_volume
from recommendations import RACE_DATE, build_recommendation, recommend_session, training_phase

_GARMIN_ERRORS = (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
    TimeoutError,
)


def handle_garmin_errors(func):
    """Vis en forståelig feilmelding i stedet for en rå traceback når Garmin-
    sesjonen er utløpt/API-et svikter. Uten dette ville en utløpt token gitt
    brukeren en uleselig Python-traceback midt i dashbordet."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except _GARMIN_ERRORS as e:
            st.error(
                "**Klarte ikke hente data fra Garmin Connect.**\n\n"
                f"Feil: {e}\n\n"
                "Kjør trolig `uv run python -m garmin_mcp.auth` i `garmin_mcp`-prosjektet "
                "for å friske opp innloggingen, og last siden på nytt."
            )
            st.stop()

    return wrapper


def render_session_recommendation(sport: str, sessions: list[dict]) -> None:
    """Vis anbefalt økt for gitt idrett — samme restitusjonssignaler som
    forsiden, kombinert med treningsfase og om en langtur er gjort denne uken."""
    snapshot = get_health_snapshot()
    readiness = build_recommendation(
        snapshot, sleep_history=get_sleep_trend(days=30), health_trends=get_trends(days=30)
    )
    days_left = (RACE_DATE - date.today()).days
    phase, _ = training_phase(days_left)

    session = recommend_session(sport, readiness["verdict"], phase, sessions)

    st.info(f"**Anbefalt økt i dag: {session['tittel']}**\n\n{session['beskrivelse']}")
    for reason in session["begrunnelse"]:
        st.caption(f"↳ {reason}")


def simple_sport_page(
    sport: str,
    icon: str,
    metric: str,
    chart_title: str,
    table_columns: list[str],
    show_recommendation: bool = False,
) -> None:
    """Enkel gren-side: ukentlig utvikling + siste økter. Brukes der vi ikke
    (ennå) har gren-spesifikk analyse (sykling, svømming, styrke)."""
    st.title(f"{icon} {sport}")

    sessions = get_activity_history(days=90).get(sport, [])
    if not sessions:
        st.write("Ingen økter registrert siste 90 dager.")
        return

    if show_recommendation:
        render_session_recommendation(sport, sessions)
        st.divider()

    st.caption(f"{chart_title}, siste 90 dager — utvikling uke for uke")
    st.bar_chart(pd.Series(weekly_volume(sessions, metric=metric), name=chart_title))

    st.subheader("Siste økter")
    recent = sorted(sessions, key=lambda s: s["dato"], reverse=True)[:15]
    df = pd.DataFrame(recent)[["dato", *table_columns]]
    st.dataframe(df, width="stretch", hide_index=True)
