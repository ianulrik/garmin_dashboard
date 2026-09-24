import functools
from collections.abc import Callable
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from data import (
    format_pace,
    get_activity_history,
    get_health_snapshot,
    get_hr_profile,
    get_watch_hr_zones,
    highest_hr,
    get_sleep_trend,
    get_trends,
    weekly_volume,
)
from recommendations import RACE_DATE, build_recommendation, recommend_session, training_phase
from settings import load_settings, save_setting

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
                "Kjør trolig `uv run python -m garmin_mcp.auth` i `garmin_mcp`-utvikler "
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


def _bpm(value) -> str:
    return f"{value:.0f} bpm" if value else "—"


def _zone_caption(zones: dict, source: str) -> None:
    if zones:
        st.caption(
            f"Pulssoner ({source}, nedre grense): "
            + " · ".join(f"S{n} fra {floor}" for n, floor in zones.items() if floor)
        )


def render_overview_hr_numbers() -> None:
    """Makspuls per idrett (fra innstillingene) og terskelpuls for løping."""
    max_hr = load_settings().get("makspuls") or {}
    numbers = get_hr_profile().get("Løping") or {}
    cols = st.columns(4)
    for col, sport in zip(cols, _MAX_HR_SPORTS):
        col.metric(f"Makspuls {sport.lower()}", _bpm(max_hr.get(sport)))
    cols[3].metric("Terskelpuls løping", _bpm(numbers.get("terskelpuls")))
    st.caption("Makspuls endres på hver idrettsside.")


def render_hr_numbers(sport: str, sessions: list[dict]) -> None:
    """Pulstall for én idrett: makspuls, høyeste målte puls, terskel og sonene klokka
    faktisk bruker for idretten (klokka har egne soner per idrett, som ikke alltid
    er de samme som i Garmin Connect-profilen)."""
    numbers = get_hr_profile().get(sport) or {}
    # Makspuls per idrett står på klokka og synkes ikke til Garmin Connect-API-et
    # (det oppgir samme verdi for alle idretter) — derfor legges den inn her.
    has_max_setting = sport in _MAX_HR_SPORTS
    max_hr = (load_settings().get("makspuls") or {}).get(sport)

    metrics = [("Makspuls", _bpm(max_hr))] if has_max_setting else []
    metrics.append(("Høyeste målte puls (90 d)", _bpm(highest_hr(sessions))))
    # Garmin har bare en ekte, målt terskelpuls for løping — for andre idretter er
    # profilverdien en kopi av løpeterskelen.
    if sport == "Løping":
        metrics.append(("Terskelpuls", _bpm(numbers.get("terskelpuls"))))
    if numbers.get("terskeltempo"):
        metrics.append(("Terskeltempo", f"{numbers['terskeltempo']} /km"))
    if numbers.get("ftp"):
        metrics.append(("FTP", f"{numbers['ftp']:.0f} W"))

    for col, (label, value) in zip(st.columns(4), metrics):
        col.metric(label, value)

    latest_with_hr = max((s for s in sessions if s.get("snitt_puls")), key=lambda s: s["dato"], default=None)
    if latest_with_hr:
        _zone_caption(get_watch_hr_zones(latest_with_hr["activity_id"]), f"klokka, {sport.lower()}")
    if has_max_setting:
        _max_hr_editor(sport, max_hr)


_MAX_HR_SPORTS = ("Løping", "Sykling", "Svømming")


def _max_hr_editor(sport: str, current: int | None) -> None:
    with st.popover("Endre makspuls"):
        st.caption(f"Samme verdi som på klokka: Innstillinger → Brukerprofil → Pulssoner → {sport}.")
        new_value = st.number_input(
            f"Makspuls {sport.lower()} (bpm)", min_value=120, max_value=240, value=current or 200, step=1
        )
        if st.button("Lagre", key=f"lagre_makspuls_{sport}"):
            max_hr = load_settings().get("makspuls") or {}
            max_hr[sport] = int(new_value)
            save_setting("makspuls", max_hr)
            st.rerun()


def pace_chart(pace_seconds: pd.Series, unit: str = "/km") -> alt.Chart:
    """Linjegraf for tempo med aksen i m:ss. Aksen er snudd, så raskere tempo er høyere opp."""
    df = pace_seconds.rename("sek").rename_axis("dato").reset_index()
    df["tempo"] = df["sek"].map(format_pace)
    mmss = "floor(datum.value / 60) + ':' + (datum.value % 60 < 10 ? '0' : '') + round(datum.value % 60)"
    return (
        alt.Chart(df)
        .mark_line(point=True)
        .encode(
            x=alt.X("dato:T", title=None),
            y=alt.Y(
                "sek:Q",
                title=f"Tempo ({unit})",
                scale=alt.Scale(reverse=True, zero=False),
                axis=alt.Axis(labelExpr=mmss),
            ),
            tooltip=[alt.Tooltip("dato:T", title="Dato"), alt.Tooltip("tempo:N", title=f"Tempo {unit}")],
        )
    )


def simple_sport_page(
    sport: str,
    icon: str,
    metric: str,
    chart_title: str,
    table_columns: list[str],
    show_recommendation: bool = False,
    extra_section: Callable[[], None] | None = None,
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

    render_hr_numbers(sport, sessions)
    st.divider()

    if extra_section:
        extra_section()
        st.divider()

    st.caption(f"{chart_title}, siste 90 dager — utvikling uke for uke")
    st.bar_chart(pd.Series(weekly_volume(sessions, metric=metric, days=90), name=chart_title))

    st.subheader("Siste økter")
    recent = sorted(sessions, key=lambda s: s["dato"], reverse=True)[:15]
    df = pd.DataFrame(recent)[["dato", *table_columns]]
    st.dataframe(df, width="stretch", hide_index=True)
