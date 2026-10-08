import functools
from collections import Counter

import altair as alt
import pandas as pd
import streamlit as st
from hevy_mcp.client import HevyError

from data import REFRESH_SECONDS, weekly_volume
from hevy_data import MUSCLE_NAMES, exercise_sessions, format_sets, get_strength_workouts, in_window


def _handle_hevy_errors(func):
    """Samme idé som handle_garmin_errors: forståelig melding i stedet for traceback."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except HevyError as e:
            st.error(
                "**Klarte ikke hente data fra Hevy.**\n\n"
                f"Feil: {e}\n\n"
                "Kjør trolig `uv run python -m hevy_mcp.auth` i `hevy_mcp`-mappen "
                "for å friske opp innloggingen, og last siden på nytt."
            )
            st.stop()

    return wrapper


_KG = st.column_config.NumberColumn(format="%d")


def _delta(now: float, before: float) -> str | None:
    return f"{now - before:+g}" if before else None


def _key_numbers(workouts: list[dict]) -> None:
    last, prev = in_window(workouts, 30), in_window(workouts, 60, 30)
    sets_now, sets_prev = (sum(w.get("arbeidssett", 0) for w in ws) for ws in (last, prev))
    vol_now, vol_prev = (sum(w.get("totalt_volum_kg", 0) for w in ws) / 1000 for ws in (last, prev))
    per_week = len(in_window(workouts, 84)) / 12

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Økter (30 d)", len(last), _delta(len(last), len(prev)))
    c2.metric("Snitt økter/uke (12 uker)", f"{per_week:.1f}")
    c3.metric("Arbeidssett (30 d)", sets_now, _delta(sets_now, sets_prev))
    c4.metric("Volum (30 d)", f"{vol_now:.1f} tonn", f"{vol_now - vol_prev:+.1f} tonn" if vol_prev else None)
    st.caption("Endring er mot de 30 dagene før. Oppvarmingssett er ikke med.")


def _weekly_charts(workouts: list[dict]) -> None:
    sessions = [
        {"dato": w["dato"], "volum": w.get("totalt_volum_kg", 0) / 1000, "sett": w.get("arbeidssett", 0)}
        for w in in_window(workouts, 90)
    ]
    left, right = st.columns(2)
    with left:
        st.caption("Volum per uke (tonn), siste 90 dager")
        st.bar_chart(pd.Series(weekly_volume(sessions, metric="volum", days=90), name="Volum (tonn)"))
    with right:
        st.caption("Arbeidssett per uke, siste 90 dager")
        st.bar_chart(pd.Series(weekly_volume(sessions, metric="sett", days=90), name="Arbeidssett"))


def _muscle_balance(workouts: list[dict]) -> None:
    sets: Counter = Counter()
    for w in in_window(workouts, 30):
        for ex in w["ovelser"]:
            muscle = MUSCLE_NAMES.get(ex.get("muskelgruppe"), ex.get("muskelgruppe") or "Ukjent")
            sets[muscle] += ex.get("arbeidssett", 0)
    if not sets:
        return
    st.subheader("Arbeidssett per muskelgruppe (30 d)")
    df = pd.DataFrame(sets.most_common(), columns=["muskelgruppe", "sett"])
    st.altair_chart(
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("sett:Q", title="Arbeidssett"),
            y=alt.Y("muskelgruppe:N", title=None, sort="-x"),
            tooltip=[alt.Tooltip("muskelgruppe:N", title="Muskelgruppe"), alt.Tooltip("sett:Q", title="Sett")],
        ),
        width="stretch",
    )
    st.caption("Etter primær muskelgruppe for hver øvelse, slik Hevy klassifiserer den.")


def _exercise_progress(workouts: list[dict]) -> None:
    st.subheader("Progresjon per øvelse")
    freq: Counter = Counter()
    names: dict[str, str] = {}
    for w in in_window(workouts, 180):
        for ex in w["ovelser"]:
            freq[ex["ovelse_id"]] += 1
            names[ex["ovelse_id"]] = ex["ovelse"]
    if not freq:
        st.write("Ingen øvelser logget siste 180 dager.")
        return

    exercise_id = st.selectbox(
        "Øvelse (sortert etter hvor ofte du har gjort den siste 180 dager)",
        [eid for eid, _ in freq.most_common()],
        format_func=lambda eid: f"{names[eid]} ({freq[eid]} økter)",
    )
    rows = exercise_sessions(workouts, exercise_id)
    added_weight = any(r.get("kg_er_tilleggsvekt") for r in rows)

    best_kg = max(rows, key=lambda r: r.get("maks_kg") or 0)
    best_1rm = max(rows, key=lambda r: r.get("estimert_1rm_kg") or 0)
    c1, c2, c3 = st.columns(3)
    c1.metric("Tyngste vekt", f"{best_kg.get('maks_kg') or 0:g} kg", best_kg["dato"], delta_color="off")
    c2.metric("Beste estimerte 1RM", f"{best_1rm.get('estimert_1rm_kg') or 0:g} kg", best_1rm["dato"], delta_color="off")
    c3.metric("Gjort totalt", f"{len(rows)} ganger", f"sist {rows[-1]['dato']}", delta_color="off")
    if added_weight:
        st.caption("Kroppsvektøvelse: kg er tilleggsvekt, ikke total vekt.")

    df = pd.DataFrame(
        [
            {"dato": r["dato"], "Estimert 1RM": r.get("estimert_1rm_kg"), "Tyngste sett": r.get("maks_kg")}
            for r in rows
        ]
    ).melt("dato", var_name="mål", value_name="kg").dropna()
    if not df.empty:
        st.altair_chart(
            alt.Chart(df)
            .mark_line(point=True)
            .encode(
                x=alt.X("dato:T", title=None),
                y=alt.Y("kg:Q", title="kg", scale=alt.Scale(zero=False)),
                color=alt.Color("mål:N", title=None, legend=alt.Legend(orient="top")),
                tooltip=[alt.Tooltip("dato:T", title="Dato"), "mål:N", alt.Tooltip("kg:Q", title="kg")],
            ),
            width="stretch",
        )
        st.caption("Estimert 1RM (Epley) regnes bare fra sett med 12 reps eller færre.")

    table = pd.DataFrame(
        [
            {
                "dato": r["dato"],
                "økt": r.get("okt"),
                "sett": format_sets(r.get("sett", [])),
                "beste sett": r.get("beste_sett"),
                "volum (kg)": r.get("volum_kg"),
                "notat": r.get("notat"),
            }
            for r in reversed(rows)
        ]
    )
    st.dataframe(table, width="stretch", hide_index=True, column_config={"volum (kg)": _KG})


def _recent_workouts(workouts: list[dict]) -> None:
    st.subheader("Siste økter")
    table = pd.DataFrame(
        [
            {
                "dato": w["dato"],
                "økt": w.get("tittel"),
                "varighet (min)": w.get("varighet_min"),
                "øvelser": w.get("antall_ovelser"),
                "arbeidssett": w.get("arbeidssett"),
                "volum (kg)": w.get("totalt_volum_kg"),
                "PR": "🏆" * sum(1 for ex in w["ovelser"] for s in ex.get("sett", []) if s.get("pr")),
            }
            for w in workouts[:15]
        ]
    )
    st.dataframe(table, width="stretch", hide_index=True, column_config={"volum (kg)": _KG})

    for w in workouts[:5]:
        with st.expander(f"{w['dato']} · {w.get('tittel')} · {w.get('varighet_min', '–')} min"):
            if w.get("beskrivelse"):
                st.caption(f"💬 {w['beskrivelse']}")
            for ex in w["ovelser"]:
                line = f"**{ex['ovelse']}**: {format_sets(ex.get('sett', []))}"
                if ex.get("notat"):
                    line += f"  \n_{ex['notat']}_"
                st.markdown(line)
    st.caption("🏆 = ny personlig rekord ifølge Hevy · (d) = dropsett · (f) = til failure")


@st.fragment(run_every=REFRESH_SECONDS)
@_handle_hevy_errors
def render() -> None:
    st.title("🏋️ Styrke")
    st.caption("Data fra Hevy")

    workouts = get_strength_workouts()
    if not workouts:
        st.write("Ingen økter i Hevy ennå.")
        return

    _key_numbers(workouts)
    st.divider()
    _weekly_charts(workouts)
    st.divider()
    _muscle_balance(workouts)
    st.divider()
    _exercise_progress(workouts)
    st.divider()
    _recent_workouts(workouts)
