import pandas as pd
import streamlit as st

from data import REFRESH_SECONDS, get_activity_history, weekly_volume
from views._common import handle_garmin_errors, render_hr_numbers, render_session_recommendation


@st.fragment(run_every=REFRESH_SECONDS)
@handle_garmin_errors
def render() -> None:
    st.title("🚴 Sykling")

    # Inkluderer spinning/innendørssykling (Garmin: indoor_cycling), merket som "Spinning".
    sessions = get_activity_history(days=90).get("Sykling", [])
    if not sessions:
        st.write("Ingen sykkeløkter registrert siste 90 dager.")
        return

    render_session_recommendation("Sykling", sessions)
    st.divider()

    render_hr_numbers("Sykling", sessions)
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.caption("Ukentlig distanse (km), siste 90 dager")
        st.bar_chart(pd.Series(weekly_volume(sessions, "distanse_km", days=90), name="km"))
    with col2:
        # Spinning har ofte ingen reell distanse — tid viser volumet riktigere.
        st.caption("Ukentlig tid (timer), ute og spinning, siste 90 dager")
        weekly_hours = {w: m / 60 for w, m in weekly_volume(sessions, "varighet_min", days=90).items()}
        st.bar_chart(pd.Series(weekly_hours, name="timer"))

    st.divider()

    st.caption("Watt per økt — snitt og normalisert (NP)")
    watt_df = pd.DataFrame(
        {
            s["dato"][:10]: {"Snitt watt": s.get("snitt_watt"), "Normalisert watt": s.get("normalisert_watt")}
            for s in sessions
            if s.get("snitt_watt")
        }
    ).T.sort_index()
    if watt_df.empty:
        st.write("Ingen økter med wattdata siste 90 dager.")
    else:
        watt_df.index = pd.to_datetime(watt_df.index)
        st.line_chart(watt_df.dropna(axis=1, how="all"))

    st.divider()

    st.subheader("Siste økter")
    recent = sorted(sessions, key=lambda s: s["dato"], reverse=True)[:15]
    df = pd.DataFrame(recent)[
        [
            "dato",
            "navn",
            "type",
            "varighet_min",
            "distanse_km",
            "fart_kmh",
            "snitt_watt",
            "normalisert_watt",
            "maks_watt",
            "snitt_puls",
        ]
    ]
    df["type"] = df["type"].fillna("Ute")
    st.dataframe(df, width="stretch", hide_index=True)
