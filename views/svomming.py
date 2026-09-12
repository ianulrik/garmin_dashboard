import streamlit as st

from data import REFRESH_SECONDS
from views._common import handle_garmin_errors, simple_sport_page


@st.fragment(run_every=REFRESH_SECONDS)
@handle_garmin_errors
def render() -> None:
    simple_sport_page(
        sport="Svømming",
        icon="🏊",
        metric="distanse_km",
        chart_title="Ukentlig distanse (km)",
        table_columns=["navn", "varighet_min", "distanse_km", "snitt_puls"],
        show_recommendation=True,
    )
