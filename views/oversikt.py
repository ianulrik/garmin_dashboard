from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from data import (
    REFRESH_SECONDS,
    get_health_snapshot,
    get_sleep_trend,
    get_trends,
    get_vo2max_trend,
    get_weekly_load_trend,
    get_weekly_training_balance,
)
from recommendations import RACE_DATE, build_recommendation, training_phase
from views._common import handle_garmin_errors, render_overview_hr_numbers


# Garmins trainingBalanceFeedbackPhrase → norsk.
_FOCUS_FEEDBACK = {
    "BALANCED": "Balansert.",
    "AEROBIC_LOW_FOCUS": "Fokus på lett aerob.",
    "AEROBIC_HIGH_FOCUS": "Fokus på høy aerob.",
    "ANAEROBIC_FOCUS": "Fokus på anaerob.",
    "AEROBIC_LOW_SHORTAGE": "For lite lett aerob.",
    "AEROBIC_HIGH_SHORTAGE": "For lite høy aerob.",
    "ANAEROBIC_SHORTAGE": "For lite anaerob.",
    "ABOVE_TARGETS": "Over de optimale områdene.",
    "BELOW_TARGETS": "Under de optimale områdene.",
    "WITHIN_TARGETS": "Innenfor de optimale områdene.",
}


def _load_focus_chart(manedlig: dict) -> alt.Chart:
    """Samme graf som «Belastningsfokus» i Garmin-appen: belastning siste 4 uker i
    anaerob, høy aerob og lett aerob, med optimalt område for hver."""
    rows = [
        ("Anaerob", manedlig["anaerob"], *manedlig["anaerob_mal"], "#b45fd6"),
        ("Høy aerob", manedlig["aerob_hoy"], *manedlig["aerob_hoy_mal"], "#f5a623"),
        ("Lett aerob", manedlig["aerob_lav"], *manedlig["aerob_lav_mal"], "#2fb5d8"),
    ]
    df = pd.DataFrame(rows, columns=["type", "belastning", "min", "maks", "farge"])
    df["belastning"] = df["belastning"].round()
    y = alt.Y("type:N", title=None, sort=None, axis=alt.Axis(labelFontSize=13))
    color = alt.Color("farge:N", scale=None)
    tooltip = [
        alt.Tooltip("type:N", title="Type"),
        alt.Tooltip("belastning:Q", title="Belastning", format=".0f"),
        alt.Tooltip("min:Q", title="Optimalt fra"),
        alt.Tooltip("maks:Q", title="Optimalt til"),
    ]
    target = (
        alt.Chart(df)
        .mark_bar(opacity=0.18, stroke="gray", strokeDash=[4, 3], strokeWidth=1.5, size=34)
        .encode(y=y, x=alt.X("min:Q", title="Belastning"), x2="maks:Q", color=color, tooltip=tooltip)
    )
    bars = alt.Chart(df).mark_bar(size=18, cornerRadiusEnd=4).encode(y=y, x="belastning:Q", color=color, tooltip=tooltip)
    labels = (
        alt.Chart(df)
        .mark_text(align="left", dx=6, fontWeight="bold")
        .encode(y=y, x="belastning:Q", text=alt.Text("belastning:Q", format=".0f"))
    )
    return (target + bars + labels).properties(height=170)


def _spo2_chart(readings: list[dict]) -> alt.Chart:
    df = pd.DataFrame(readings)
    df["tid"] = pd.to_datetime(df["tid"])
    return (
        alt.Chart(df)
        .mark_line(interpolate="monotone")
        .encode(
            x=alt.X("tid:T", title=None, axis=alt.Axis(format="%H:%M")),
            y=alt.Y("spo2:Q", title="SpO2 (%)", scale=alt.Scale(domain=[min(85, df["spo2"].min()), 100])),
            tooltip=[alt.Tooltip("tid:T", title="Tid", format="%H:%M"), alt.Tooltip("spo2:Q", title="SpO2 %")],
        )
        .properties(height=200)
    )


def _load_chart(load_trend: dict[str, float]) -> alt.Chart:
    """Søyler for ukentlig belastning + linje for 4-ukers glidende snitt, så brå
    hopp i belastning skiller seg ut mot det du er vant til."""
    df = pd.DataFrame({"uke": list(load_trend), "belastning": list(load_trend.values())})
    df["snitt_4_uker"] = df["belastning"].rolling(4, min_periods=1).mean().round()
    base = alt.Chart(df).encode(x=alt.X("uke:N", title=None, sort=None))
    bars = base.mark_bar(opacity=0.7).encode(
        y=alt.Y("belastning:Q", title="Belastning"),
        tooltip=[alt.Tooltip("uke:N", title="Uke"), alt.Tooltip("belastning:Q", title="Belastning", format=".0f")],
    )
    line = base.mark_line(point=True, color="#e45756").encode(
        y="snitt_4_uker:Q",
        tooltip=[alt.Tooltip("uke:N", title="Uke"), alt.Tooltip("snitt_4_uker:Q", title="4-ukers snitt")],
    )
    return bars + line


@st.fragment(run_every=REFRESH_SECONDS)
@handle_garmin_errors
def render() -> None:
    st.title("Treningsdashboard")

    days_left = (RACE_DATE - date.today()).days
    phase, phase_desc = training_phase(days_left)
    st.caption(
        f"**{days_left} dager** til Ironman 70.3 Jönköping ({RACE_DATE.isoformat()}) — "
        f"**fase: {phase}**. {phase_desc}"
    )

    snapshot = get_health_snapshot()
    # 30 dagers historikk brukes både til å kalibrere anbefalingen mot ditt
    # eget snitt (se recommendations.py) og til trendgrafene lenger ned.
    sleep_trend = get_sleep_trend(days=30)
    trends = get_trends(days=30)
    recommendation = build_recommendation(snapshot, sleep_history=sleep_trend, health_trends=trends)

    verdict_colors = {
        "Hviledag eller lett økt": "🔴",
        "Ta det litt roligere i dag": "🟡",
        "Normal treningsdag": "🟢",
        "Klar for en hardøkt": "🟢",
    }
    st.subheader(f"{verdict_colors.get(recommendation['verdict'], '')} {recommendation['verdict']}")
    for flag in recommendation["flags"]:
        st.write(f"- ⚠️ {flag}")
    for positive in recommendation["positives"]:
        st.write(f"- ✅ {positive}")

    st.divider()

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    sovn = snapshot["sovn"]
    hrv = snapshot["hrv"]
    trening = snapshot["trening"]
    bb = snapshot["body_battery"]

    col1.metric("Søvn i natt", f"{sovn['total_min'] / 60:.1f} t", sovn.get("kvalitet"))
    col2.metric("HRV (siste natt)", f"{hrv.get('siste_natt_ms') or '—'} ms", hrv.get("status"))
    col3.metric("Hvilepuls", f"{snapshot.get('hvilepuls') or '—'} bpm")
    col4.metric("Body Battery", f"{bb.get('naa') or '—'} / 100")
    col5.metric("VO2max", trening.get("vo2max") or "—")
    col6.metric(
        "Belastningsforhold",
        trening.get("belastningsforhold") or "—",
        trening.get("belastning_status"),
    )

    st.divider()

    st.subheader("❤️ Puls")
    render_overview_hr_numbers()

    st.divider()

    st.subheader("🔬 Kondisjon (VO2maks)")
    vo2_trend = get_vo2max_trend(months=6)
    loping_vo2 = vo2_trend["loping"]

    if loping_vo2:
        vo2_col1, vo2_col2 = st.columns([1, 3])
        values = list(loping_vo2.values())
        endring = values[-1] - values[0]
        with vo2_col1:
            st.metric(
                "VO2maks (løping)",
                f"{values[-1]:.1f}",
                f"{endring:+.1f} siste 6 mnd",
            )
        with vo2_col2:
            st.caption("VO2maks-utvikling, siste 6 måneder")
            vo2_series = pd.Series(loping_vo2, name="VO2maks")
            vo2_series.index = pd.to_datetime(vo2_series.index)
            st.line_chart(vo2_series)
    else:
        st.write("Ingen VO2maks-data tilgjengelig ennå.")

    if vo2_trend["sykling"]:
        st.caption("VO2maks-utvikling sykling, siste 6 måneder")
        cycling_series = pd.Series(vo2_trend["sykling"], name="VO2maks sykling")
        cycling_series.index = pd.to_datetime(cycling_series.index)
        st.line_chart(cycling_series)

    st.divider()

    st.subheader("⚖️ Treningsbalanse og belastning")

    bal_col, load_col = st.columns(2)
    with bal_col:
        st.caption("Ukentlige timer per idrett, siste 12 uker")
        balance = get_weekly_training_balance(days=84)
        balance_df = pd.DataFrame(balance).fillna(0.0)
        if not balance_df.empty:
            # Stablede søyler: hver uke er en egen enhet, og totalhøyden viser ukens samlede timer.
            st.bar_chart(balance_df, stack=True)
        else:
            st.write("Ingen økter registrert ennå.")

    with load_col:
        st.caption("Ukentlig treningsbelastning, alle idretter (siste 90 dager) — linjen er 4-ukers snitt")
        load_trend = get_weekly_load_trend(days=90)
        if load_trend:
            st.altair_chart(_load_chart(load_trend), width="stretch")
        else:
            st.write("Ingen belastningsdata ennå.")

    manedlig = trening.get("manedlig_balanse") or {}
    if manedlig.get("aerob_lav") is not None:
        st.markdown("**Belastningsfokus, siste 4 uker**")
        feedback = manedlig.get("feedback")
        st.caption(
            f"Garmins vurdering: **{_FOCUS_FEEDBACK.get(feedback, feedback or '—')}** "
            "Den skraverte boksen er optimalt område for hver type."
        )
        st.altair_chart(_load_focus_chart(manedlig), width="stretch")

    st.divider()

    st.subheader("😴 Søvn")
    sleep_col1, sleep_col2 = st.columns([2, 3])

    with sleep_col1:
        retning_tekst = {"INCREASED": "økt", "DECREASED": "redusert", "NO_CHANGE": "uendret"}
        retning = retning_tekst.get(sovn.get("anbefaling_retning"), sovn.get("anbefaling_retning") or "—")
        if sovn.get("anbefalt_justert_min"):
            st.info(
                f"**Garmins søvnanbefaling for i natt:** "
                f"{sovn['anbefalt_justert_min'] / 60:.1f} t (normalt {sovn.get('anbefalt_naa_min', 0) / 60:.1f} t, {retning} "
                f"pga. treningsbelastning/HRV)."
            )
        st.write(f"**Dyp søvn:** {sovn.get('dyp_min', 0):.0f} min")
        st.write(f"**Lett søvn:** {sovn.get('lett_min', 0):.0f} min")
        st.write(f"**REM-søvn:** {sovn.get('rem_min', 0):.0f} min")
        st.write(f"**Våken:** {sovn.get('vaken_min', 0):.0f} min ({sovn.get('antall_oppvakninger', 0)} oppvåkninger)")
        st.write(f"**Snitt søvnstress:** {sovn.get('snitt_stress') or '—'}")
        if sovn.get("spo2_snitt"):
            st.write(
                f"**SpO2:** snitt {sovn['spo2_snitt']:.0f} %, laveste {sovn.get('spo2_laveste') or '—'} %, "
                f"høyeste {sovn.get('spo2_hoyeste') or '—'} %"
            )

    with sleep_col2:
        sleep_df = pd.DataFrame(sleep_trend).set_index("dato")
        sleep_df.index = pd.to_datetime(sleep_df.index)

        st_col_a, st_col_b = st.columns(2)
        with st_col_a:
            st.caption("Søvnvarighet, siste 30 dager (timer)")
            st.line_chart(sleep_df["timer"])
        with st_col_b:
            st.caption("Søvnscore, siste 30 dager")
            st.line_chart(sleep_df["score"])

        if sovn.get("spo2_natt"):
            st.caption(f"SpO2 gjennom natta ({sovn['dato']}), %")
            st.altair_chart(_spo2_chart(sovn["spo2_natt"]), width="stretch")

    st.divider()

    st.subheader("📈 Trender (siste 30 dager)")
    trend_df = pd.DataFrame(
        {
            "Hvilepuls": pd.Series(trends["hvilepuls"]),
            "HRV": pd.Series(trends["hrv"]),
        }
    )
    trend_df.index = pd.to_datetime(trend_df.index)
    trend_df = trend_df.sort_index()

    tcol1, tcol2 = st.columns(2)
    with tcol1:
        st.caption("Hvilepuls (bpm)")
        st.line_chart(trend_df["Hvilepuls"])
    with tcol2:
        st.caption("HRV, siste natt (ms)")
        st.line_chart(trend_df["HRV"])
