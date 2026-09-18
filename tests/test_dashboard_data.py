import json
import sqlite3

import pandas as pd

from dashboard_data import (
    add_live_scores,
    build_alerts,
    dataframe_to_json_bytes,
    prepare_dashboard_data,
)


def make_database(path):
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE candidates (id INTEGER PRIMARY KEY, full_name TEXT, email TEXT, password TEXT, photo_filename TEXT);
        CREATE TABLE exam_sessions (id INTEGER PRIMARY KEY, candidate_id INTEGER, exam_name TEXT, status TEXT, started_at TEXT, submitted_at TEXT, created_at TEXT);
        CREATE TABLE session_events (id INTEGER PRIMARY KEY, session_id INTEGER, event_type TEXT, event_timestamp TEXT, details TEXT, duration_seconds REAL);
        CREATE TABLE session_integrity_reports (session_id INTEGER PRIMARY KEY, integrity_score REAL, risk_label TEXT, face_presence_ratio REAL, event_penalty REAL, presence_penalty REAL, face_absent_duration REAL, report_text TEXT, generated_at TEXT);
        INSERT INTO candidates VALUES (1, 'Asha', 'asha@example.com', 'x', NULL);
        INSERT INTO exam_sessions VALUES (1, 1, 'Python', 'submitted', '2026-01-01T10:00:00+00:00', '2026-01-01T10:10:00+00:00', '2026-01-01T10:00:00+00:00'), (2, 1, 'SQL', 'in_progress', '2026-01-01T11:00:00+00:00', NULL, '2026-01-01T11:00:00+00:00');
        INSERT INTO session_events VALUES (1, 1, 'tab_switch', '2026-01-01T10:02:00+00:00', 'Changed tab', 0), (2, 1, 'multiple_faces', '2026-01-01T10:03:00+00:00', '2 faces', 0), (3, 2, 'no_face', '2026-01-01T11:01:00+00:00', 'Face was absent for 15 seconds.', 15);
        INSERT INTO session_integrity_reports VALUES (1, 90, 'Low', 1, 10, 0, 0, 'Validated report', '2026-01-01T10:10:00+00:00');
        """
    )
    connection.commit()
    connection.close()


def test_live_database_pipeline_returns_sessions_events_alerts(tmp_path):
    database = tmp_path / "examguard.db"
    make_database(database)
    data = prepare_dashboard_data(str(database))

    assert len(data["sessions"]) == 2
    assert len(data["events"]) == 3
    assert set(data["alerts"]["event_type"]) == {"tab_switch", "multiple_faces", "no_face"}
    assert data["sessions"].loc[data["sessions"]["session_id"] == 1, "report_text"].item() == "Validated report"
    assert data["sessions"]["cluster"].notna().all()


def test_multiple_faces_is_scored_and_alerted():
    sessions = pd.DataFrame([{"session_id": 1, "started_at": "2026-01-01T10:00:00+00:00", "submitted_at": "2026-01-01T10:10:00+00:00", "integrity_score": pd.NA}])
    events = pd.DataFrame([{"event_id": 1, "session_id": 1, "event_type": "multiple_faces", "event_timestamp": "2026-01-01T10:01:00+00:00", "details": "Two faces", "duration_seconds": 0}])
    scored = add_live_scores(sessions, events)
    alerts = build_alerts(events)

    assert scored["integrity_score"].item() == 95.0
    assert alerts["alert_level"].item() == "High"


def test_json_export_is_valid_records():
    payload = dataframe_to_json_bytes(pd.DataFrame([{"session_id": 1, "score": 95.0}]))
    assert json.loads(payload) == [{"session_id": 1, "score": 95.0}]
