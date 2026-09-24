import pandas as pd
import streamlit as st

from data import (
    REFRESH_SECONDS,
    get_activity_history,
    get_race_predictions,
    hr_zone_distribution,
    weekly_longest,
    weekly_volume,
)
from views._common import handle_garmin_errors, pace_chart, render_hr_numbers, render_session_recommendation

ZONE_LABELS = {
    1: "Sone 1 (oppvarming)",
    2: "Sone 2 (rolig/aerob)",
    3: "Sone 3 (moderat)",
    4: "Sone 4 (terskel)",
    5: "Sone 5 (maks)",
}


@st.fragment(run_every=REFRESH_SECONDS)
@handle_garmin_errors
def render() -> None:
    st.title("🏃 Løping")

    sessions = get_activity_history(days=90).get("Løping", [])
    if not sessions:
        st.write("Ingen løpeøkter registrert siste 90 dager.")
        return

    render_session_recommendation("Løping", sessions)
    st.divider()

    render_hr_numbers("Løping", sessions)
    st.divider()

    predictions = get_race_predictions()
    if any(predictions.values()):
        st.caption("Garmins estimerte løpstider basert på nåværende form")
        pred_cols = st.columns(len(predictions))
        for col, (distance, time) in zip(pred_cols, predictions.items()):
            col.metric(distance, time or "—")
        st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.caption("Ukentlig distanse (km), siste 90 dager")
        st.bar_chart(pd.Series(weekly_volume(sessions, "distanse_km", days=90), name="km"))
    with col2:
        st.caption("Lengste langtur per uke (km) — progresjon mot 70.3-distansen")
        st.bar_chart(pd.Series(weekly_longest(sessions, "distanse_km", days=90), name="km"))

    st.divider()

    col3, col4 = st.columns(2)
    with col3:
        st.caption("Tempo per økt (min/km) — høyere opp er raskere")
        pace_series = pd.Series(
            {s["dato"][:10]: s["tempo_sek_per_km"] for s in sessions if s.get("tempo_sek_per_km")}
        ).sort_index()
        pace_series.index = pd.to_datetime(pace_series.index)
        st.altair_chart(pace_chart(pace_series), width="stretch")
    with col4:
        st.caption("Kadens per økt (skritt/min)")
        cadence_series = pd.Series(
            {s["dato"][:10]: s["kadens"] for s in sessions if s.get("kadens")}
        ).sort_index()
        cadence_series.index = pd.to_datetime(cadence_series.index)
        st.line_chart(cadence_series)

    st.divider()

    st.caption("Pulssone-fordeling, siste 90 dager (minutter) — er balansen mellom rolig og hardt riktig?")
    zone_totals = hr_zone_distribution(sessions)
    zone_df = pd.Series({ZONE_LABELS[z]: minutes for z, minutes in zone_totals.items()})
    st.bar_chart(zone_df)

    st.divider()

    st.subheader("Siste økter")
    recent = sorted(sessions, key=lambda s: s["dato"], reverse=True)[:15]
    df = pd.DataFrame(recent)[
        [
            "dato",
            "navn",
            "distanse_km",
            "varighet_min",
            "tempo_min_per_km",
            "snitt_puls",
            "kadens",
            "hoydemeter",
            "treningseffekt",
        ]
    ]
    st.dataframe(df, width="stretch", hide_index=True)
