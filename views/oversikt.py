from datetime import date

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
from views._common import handle_garmin_errors


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
            st.area_chart(balance_df)
        else:
            st.write("Ingen økter registrert ennå.")

    with load_col:
        st.caption("Ukentlig treningsbelastning, alle idretter (siste 90 dager)")
        load_trend = get_weekly_load_trend(days=90)
        if load_trend:
            st.bar_chart(pd.Series(load_trend, name="Belastning"))
        else:
            st.write("Ingen belastningsdata ennå.")

    manedlig = trening.get("manedlig_balanse") or {}
    if manedlig.get("feedback"):
        feedback_tekst = {
            "ABOVE_TARGETS": "Over Garmins anbefalte målsoner denne måneden.",
            "BELOW_TARGETS": "Under Garmins anbefalte målsoner denne måneden.",
            "WITHIN_TARGETS": "Innenfor Garmins anbefalte målsoner denne måneden.",
        }
        st.caption(
            f"Garmins månedsvurdering: **{feedback_tekst.get(manedlig['feedback'], manedlig['feedback'])}** "
            f"(aerob lav {manedlig['aerob_lav']:.0f}, mål {manedlig['aerob_lav_mal'][0]}–{manedlig['aerob_lav_mal'][1]}; "
            f"aerob høy {manedlig['aerob_hoy']:.0f}, mål {manedlig['aerob_hoy_mal'][0]}–{manedlig['aerob_hoy_mal'][1]}; "
            f"anaerob {manedlig['anaerob']:.0f}, mål {manedlig['anaerob_mal'][0]}–{manedlig['anaerob_mal'][1]})"
        )

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

    st.divider()

    st.subheader("📈 Trender (siste 30 dager)")
    trend_df = pd.DataFrame(
        {
            "Hvilepuls": pd.Series(trends["hvilepuls"]),
            "HRV": pd.Series(trends["hrv"]),
            "Body Battery (ladet)": pd.Series(trends["body_battery_ladet"]),
        }
    )
    trend_df.index = pd.to_datetime(trend_df.index)
    trend_df = trend_df.sort_index()

    tcol1, tcol2, tcol3 = st.columns(3)
    with tcol1:
        st.caption("Hvilepuls (bpm)")
        st.line_chart(trend_df["Hvilepuls"])
    with tcol2:
        st.caption("HRV, siste natt (ms)")
        st.line_chart(trend_df["HRV"])
    with tcol3:
        st.caption("Body Battery ladet (poeng)")
        st.line_chart(trend_df["Body Battery (ladet)"])
