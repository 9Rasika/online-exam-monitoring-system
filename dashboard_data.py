"""Shared data access and analytics for the administrator dashboard.

The candidate-facing Flask application writes to ``examguard.db``.  This
module is deliberately read-only: Streamlit, exports, and tests can therefore
use the same prepared data without changing examination records.
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any

import pandas as pd

from scoring import calculate_integrity_score


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "examguard.db")
SUSPICIOUS_EVENT_TYPES = {
    "tab_switch", "window_focus_lost", "focus_lost", "no_face",
    "face_absent", "multiple_faces",
}


def get_connection(database_path: str = DATABASE) -> sqlite3.Connection:
    """Open the application database in read-only usage mode."""
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def load_dashboard_data(database_path: str = DATABASE) -> dict[str, pd.DataFrame]:
    """Load sessions, monitoring events, and stored AI integrity reports."""
    with get_connection(database_path) as connection:
        sessions = pd.read_sql_query(
            """
            SELECT es.id AS session_id, es.candidate_id, c.full_name AS candidate_name,
                   c.email AS candidate_email, es.exam_name, es.status,
                   es.started_at, es.submitted_at, es.created_at,
                   sir.integrity_score, sir.risk_label, sir.face_presence_ratio,
                   sir.event_penalty, sir.presence_penalty,
                   sir.face_absent_duration, sir.report_text, sir.generated_at
            FROM exam_sessions AS es
            JOIN candidates AS c ON c.id = es.candidate_id
            LEFT JOIN session_integrity_reports AS sir ON sir.session_id = es.id
            ORDER BY es.id DESC
            """,
            connection,
        )
        events = pd.read_sql_query(
            """
            SELECT id AS event_id, session_id, event_type, event_timestamp,
                   details, duration_seconds
            FROM session_events
            ORDER BY event_timestamp DESC, id DESC
            """,
            connection,
        )
    return {"sessions": sessions, "events": events}


def add_live_scores(sessions: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Fill score fields for active sessions without overwriting final scores."""
    result = sessions.copy()
    if result.empty:
        return result

    score_columns = [
        "integrity_score", "risk_label", "face_presence_ratio", "event_penalty",
        "presence_penalty", "face_absent_duration",
    ]
    for column in score_columns:
        if column not in result:
            result[column] = pd.NA

    for index, session in result.iterrows():
        if pd.notna(session["integrity_score"]):
            continue
        session_events = events[events["session_id"] == session["session_id"]]
        score = calculate_integrity_score(
            session_events,
            exam_start=session["started_at"],
            exam_end=session["submitted_at"],
        )
        for column in score_columns:
            result.at[index, column] = score[column]
    return result


def build_alerts(events: pd.DataFrame) -> pd.DataFrame:
    """Turn suspicious monitoring events into reviewable alert/evidence rows."""
    columns = [
        "event_id", "session_id", "event_type", "event_timestamp", "details",
        "duration_seconds", "alert_level", "evidence_status", "review_status",
        "evidence_description",
    ]
    if events.empty:
        return pd.DataFrame(columns=columns)

    alerts = events[events["event_type"].isin(SUSPICIOUS_EVENT_TYPES)].copy()
    if alerts.empty:
        return pd.DataFrame(columns=columns)
    alerts["alert_level"] = "Medium"
    alerts.loc[alerts["event_type"].isin({"no_face", "face_absent", "multiple_faces"}), "alert_level"] = "High"
    alerts["evidence_status"] = "Available"
    alerts["review_status"] = "Pending"
    alerts["evidence_description"] = (
        alerts["event_type"].str.replace("_", " ").str.title()
    )
    return alerts[columns]


def add_cluster_assignments(sessions: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Assign behavioural-risk clusters from session-level monitoring features."""
    result = sessions.copy()
    result["cluster"] = "Not available"
    result["behavioural_risk_cluster"] = "Not available"
    if result.empty:
        return result

    aliases = {"focus_lost": "window_focus_lost", "face_absent": "no_face"}
    normalised_events = events.copy()
    if not normalised_events.empty:
        normalised_events["event_type"] = normalised_events["event_type"].replace(aliases)

    rows: list[dict[str, Any]] = []
    for _, session in result.iterrows():
        session_events = normalised_events[
            normalised_events["session_id"] == session["session_id"]
        ]
        rows.append({
            "session_id": session["session_id"],
            "tab_switch_count": int((session_events["event_type"] == "tab_switch").sum()),
            "focus_lost_count": int((session_events["event_type"] == "window_focus_lost").sum()),
            "face_absent_count": int((session_events["event_type"] == "no_face").sum()),
            "face_absent_duration": float(
                session_events.loc[session_events["event_type"] == "no_face", "duration_seconds"].fillna(0).sum()
            ),
            "integrity_score": float(session["integrity_score"]),
        })
    features = pd.DataFrame(rows)

    if len(features) == 1:
        assignments = pd.Series([0], index=features.index)
    else:
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler

        feature_columns = [
            "tab_switch_count", "focus_lost_count", "face_absent_count",
            "face_absent_duration", "integrity_score",
        ]
        cluster_count = min(3, len(features))
        scaled = StandardScaler().fit_transform(features[feature_columns])
        assignments = pd.Series(
            KMeans(n_clusters=cluster_count, random_state=42, n_init=10).fit_predict(scaled),
            index=features.index,
        )
    features["cluster"] = assignments
    ranked_clusters = features.groupby("cluster")["integrity_score"].mean().sort_values()
    labels = ["High", "Medium", "Low"][-len(ranked_clusters):]
    risk_map = dict(zip(ranked_clusters.index, labels))
    features["behavioural_risk_cluster"] = features["cluster"].map(risk_map)
    return result.merge(
        features[["session_id", "cluster", "behavioural_risk_cluster"]],
        on="session_id", how="left", suffixes=("", "_calculated"),
    ).drop(columns=["cluster", "behavioural_risk_cluster"]).rename(
        columns={"cluster_calculated": "cluster", "behavioural_risk_cluster_calculated": "behavioural_risk_cluster"}
    )


def prepare_dashboard_data(database_path: str = DATABASE) -> dict[str, pd.DataFrame]:
    """Return all dashboard datasets derived from the live application DB."""
    raw = load_dashboard_data(database_path)
    sessions = add_live_scores(raw["sessions"], raw["events"])
    sessions = add_cluster_assignments(sessions, raw["events"])
    return {"sessions": sessions, "events": raw["events"], "alerts": build_alerts(raw["events"])}


def dataframe_to_json_bytes(dataframe: pd.DataFrame) -> bytes:
    """Create UTF-8 JSON that safely represents timestamps and null values."""
    records = json.loads(dataframe.to_json(orient="records", date_format="iso"))
    return json.dumps(records, indent=2, ensure_ascii=False).encode("utf-8")

