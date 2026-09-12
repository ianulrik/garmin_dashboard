import streamlit as st

from views import loping, oversikt, styrke, svomming, sykling

st.set_page_config(page_title="Treningsdashboard", page_icon="🏊", layout="wide")

nav = st.navigation(
    [
        st.Page(oversikt.render, title="Oversikt", icon="📊", url_path="oversikt", default=True),
        st.Page(loping.render, title="Løping", icon="🏃", url_path="loping"),
        st.Page(sykling.render, title="Sykling", icon="🚴", url_path="sykling"),
        st.Page(svomming.render, title="Svømming", icon="🏊", url_path="svomming"),
        st.Page(styrke.render, title="Styrke", icon="🏋️", url_path="styrke"),
    ]
)
nav.run()
