import streamlit as st

from data import REFRESH_SECONDS, format_pace
from settings import load_settings, parse_pace, save_setting
from views._common import handle_garmin_errors, simple_sport_page


def _render_css() -> None:
    """CSS (kritisk svømmehastighet) finnes i Garmin-appen under Ytelsesstatistikk,
    men ikke i API-et — så den legges inn her for hånd."""
    css_seconds = load_settings().get("css_sek_per_100m")

    col1, col2 = st.columns([1, 3])
    col1.metric("CSS (kritisk svømmehastighet)", f"{format_pace(css_seconds)} /100m" if css_seconds else "—")
    with col2.popover("Endre CSS"):
        st.caption("Finn den i Garmin Connect-appen: Mer → Ytelsesstatistikk → Kritisk svømmehastighet.")
        new_value = st.text_input("CSS per 100 m (m:ss)", value=format_pace(css_seconds) or "", placeholder="1:45")
        if st.button("Lagre", key="lagre_css"):
            seconds = parse_pace(new_value)
            if seconds:
                save_setting("css_sek_per_100m", seconds)
                st.rerun()
            else:
                st.error("Skriv tempoet som m:ss, f.eks. 1:45.")


@st.fragment(run_every=REFRESH_SECONDS)
@handle_garmin_errors
def render() -> None:
    simple_sport_page(
        sport="Svømming",
        icon="🏊",
        metric="distanse_km",
        chart_title="Ukentlig distanse (km)",
        table_columns=["navn", "varighet_min", "distanse_km", "tempo_per_100m", "snitt_puls"],
        show_recommendation=True,
        extra_section=_render_css,
    )
