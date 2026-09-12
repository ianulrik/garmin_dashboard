import streamlit as st

from data import REFRESH_SECONDS
from views._common import handle_garmin_errors, simple_sport_page


@st.fragment(run_every=REFRESH_SECONDS)
@handle_garmin_errors
def render() -> None:
    simple_sport_page(
        sport="Styrke",
        icon="🏋️",
        metric="varighet_min",
        chart_title="Ukentlig varighet (min)",
        table_columns=["navn", "varighet_min"],  # ingen distanse — gir ikke mening for styrke
    )
