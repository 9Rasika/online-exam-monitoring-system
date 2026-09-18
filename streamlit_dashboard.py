"""Exam Monitoring administrator dashboard. Run with ``streamlit run streamlit_dashboard.py``."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard_data import dataframe_to_json_bytes, prepare_dashboard_data


st.set_page_config(page_title="Exam Monitoring | Control Center", page_icon="🛡️", layout="wide")
st.markdown("""
<style>
    .stApp { background: #f5f7fb; color: #182033; }
    [data-testid="stSidebar"] { background: #101a33; }
    [data-testid="stSidebar"] * { color: #eaf0ff; }
    [data-testid="stSidebar"] .stButton > button { background: #3b82f6; color: white;
            border: 1px solid #60a5fa; font-weight: 800; }
    [data-testid="stSidebar"] .stButton > button:hover { background: #2563eb; color: white;
            border-color: #93c5fd; }
    .hero { background: linear-gradient(115deg, #132b58, #3465c7); border-radius: 20px;
            padding: 2.1rem 2.3rem; color: white; margin-bottom: 1.2rem; }
    .hero .eyebrow { color: #a9c5ff; font-size: .75rem; font-weight: 800; letter-spacing: .14em; }
    .hero h1 { font-size: 2rem; margin: .35rem 0; color: white; }
    .hero p { margin: 0; color: #d8e5ff; }
    [data-testid="stMetric"] { background: white; border: 1px solid #e5eaf3; border-radius: 15px;
            padding: .8rem 1rem; box-shadow: 0 3px 12px rgba(20, 43, 87, .06); }
    [data-testid="stMetricLabel"] { color: #68738a; font-weight: 700; }
    .section-label { color: #68738a; font-size: .76rem; font-weight: 800; letter-spacing: .12em;
                      margin-top: 1.5rem; }
    .panel { background: white; border: 1px solid #e5eaf3; border-radius: 15px; padding: 1rem 1.2rem;
             min-height: 80px; }
    .risk-high { color: #b4233d; font-weight: 800; }
    .risk-medium { color: #ae6300; font-weight: 800; }
    .risk-low { color: #137a4b; font-weight: 800; }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=10)
def get_data():
    """Refresh live database information at most every ten seconds."""
    return prepare_dashboard_data()


with st.sidebar:
    st.markdown("## 🛡️ Exam Monitoring")
    st.caption("ADMINISTRATOR CONTROL CENTER")
    st.divider()
    page = st.radio("Navigation", ["Overview", "Sessions", "Alerts", "Analytics", "Exports"], label_visibility="collapsed")
    st.divider()
    st.caption("Live data refreshes every 10 seconds.")
    if st.button("↻ Refresh now", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

try:
    data = get_data()
except Exception as error:
    st.error(f"Unable to load the Exam Monitoring database: {error}")
    st.stop()

sessions, events, alerts = data["sessions"], data["events"], data["alerts"]
active_sessions = int((sessions["status"] == "in_progress").sum()) if not sessions.empty else 0
high_risk = int((sessions["risk_label"] == "High").sum()) if not sessions.empty else 0
high_alerts = int((alerts["alert_level"] == "High").sum()) if not alerts.empty else 0
average_score = sessions["integrity_score"].mean() if not sessions.empty else 0

st.markdown("""
<div class="hero">
  <div class="eyebrow">EXAM INTEGRITY OPERATIONS</div>
  <h1>Monitoring Control Center</h1>
  <p>Review live activity, risk evidence, integrity results, and behavioural analytics in one place.</p>
</div>
""", unsafe_allow_html=True)


def show_metrics():
    metric_columns = st.columns(4)
    metric_columns[0].metric("Active sessions", active_sessions)
    metric_columns[1].metric("Average integrity", f"{average_score:.1f}%")
    metric_columns[2].metric("High-risk sessions", high_risk)
    metric_columns[3].metric("High-priority alerts", high_alerts)


def session_table():
    if sessions.empty:
        st.info("No examination sessions have been recorded yet.")
        return
    statuses = sorted(sessions["status"].dropna().unique())
    selected_statuses = st.multiselect("Filter by status", statuses, default=statuses)
    query = st.text_input("Search candidate, email, or exam", placeholder="e.g. Asha or Python")
    visible = sessions[sessions["status"].isin(selected_statuses)].copy()
    if query:
        search_columns = ["candidate_name", "candidate_email", "exam_name"]
        matches = visible[search_columns].fillna("").astype(str).apply(
            lambda row: row.str.contains(query, case=False, regex=False).any(), axis=1
        )
        visible = visible[matches]
    columns = ["session_id", "candidate_name", "exam_name", "status", "integrity_score", "risk_label", "behavioural_risk_cluster", "started_at", "submitted_at"]
    st.dataframe(visible.reindex(columns=columns), use_container_width=True, hide_index=True)
    st.caption(f"Showing {len(visible)} of {len(sessions)} sessions.")


def alert_table():
    if alerts.empty:
        st.success("No suspicious monitoring events are available.")
        return
    selected_levels = st.multiselect("Alert priority", ["High", "Medium"], default=["High", "Medium"])
    visible = alerts[alerts["alert_level"].isin(selected_levels)]
    st.dataframe(visible, use_container_width=True, hide_index=True)


def analytics_panels():
    if sessions.empty:
        st.info("Analytics appear after monitoring sessions are recorded.")
        return
    left, right = st.columns(2)
    with left:
        st.markdown("<div class='panel'><b>Integrity score distribution</b></div>", unsafe_allow_html=True)
        st.bar_chart(sessions["integrity_score"].value_counts(bins=10).sort_index())
    with right:
        st.markdown("<div class='panel'><b>Behavioural risk clusters</b></div>", unsafe_allow_html=True)
        st.bar_chart(sessions["behavioural_risk_cluster"].value_counts())
    if not events.empty:
        trend = events.copy()
        trend["event_timestamp"] = pd.to_datetime(trend["event_timestamp"], errors="coerce")
        trend = trend.dropna(subset=["event_timestamp"]).set_index("event_timestamp")
        st.markdown("<div class='panel'><b>Monitoring events over time</b></div>", unsafe_allow_html=True)
        st.line_chart(trend.resample("5min").size().rename("events"))


show_metrics()
if page == "Overview":
    st.markdown("<p class='section-label'>LIVE MONITORING</p>", unsafe_allow_html=True)
    session_table()
    st.markdown("<p class='section-label'>MOST RECENT ALERTS</p>", unsafe_allow_html=True)
    if alerts.empty:
        st.success("No alerts to review.")
    else:
        st.dataframe(alerts.head(8), use_container_width=True, hide_index=True)
elif page == "Sessions":
    st.markdown("<p class='section-label'>ALL EXAMINATION SESSIONS</p>", unsafe_allow_html=True)
    session_table()
elif page == "Alerts":
    st.markdown("<p class='section-label'>ALERTS AND EVIDENCE</p>", unsafe_allow_html=True)
    alert_table()
elif page == "Analytics":
    st.markdown("<p class='section-label'>DATA SCIENCE ANALYTICS</p>", unsafe_allow_html=True)
    analytics_panels()
else:
    st.markdown("<p class='section-label'>DOWNLOAD SESSION OUTPUTS</p>", unsafe_allow_html=True)
    st.caption("Export logs, integrity scores, AI reports, cluster assignments, and alerts as CSV or JSON.")
    for name, dataframe in data.items():
        with st.container(border=True):
            st.markdown(f"**{name.title()}**  ")
            csv_column, json_column = st.columns(2)
            csv_column.download_button(
                "Download CSV", dataframe.to_csv(index=False).encode("utf-8"),
                file_name=f"examguard_{name}.csv", mime="text/csv", key=f"{name}-csv",
                use_container_width=True,
            )
            json_column.download_button(
                "Download JSON", dataframe_to_json_bytes(dataframe),
                file_name=f"examguard_{name}.json", mime="application/json", key=f"{name}-json",
                use_container_width=True,
            )
