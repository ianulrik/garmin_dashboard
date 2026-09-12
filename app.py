from datetime import date

import pandas as pd
import streamlit as st

from data import get_health_snapshot, get_recent_activities, get_trends
from recommendations import build_recommendation

RACE_DATE = date(2027, 7, 11)  # Ironman 70.3 Jönköping

st.set_page_config(page_title="Treningsdashboard", page_icon="🏊", layout="wide")

st.title("Treningsdashboard")

days_left = (RACE_DATE - date.today()).days
st.caption(f"**{days_left} dager** til Ironman 70.3 Jönköping ({RACE_DATE.isoformat()})")

snapshot = get_health_snapshot()
recommendation = build_recommendation(snapshot)

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

st.subheader("Trender (siste 14 dager)")
trends = get_trends(days=14)
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
tcol1.line_chart(trend_df["Hvilepuls"])
tcol2.line_chart(trend_df["HRV"])
tcol3.line_chart(trend_df["Body Battery (ladet)"])

st.divider()

st.subheader("Siste økter")
activities_df = pd.DataFrame(get_recent_activities(limit=8))
st.dataframe(activities_df, use_container_width=True, hide_index=True)
