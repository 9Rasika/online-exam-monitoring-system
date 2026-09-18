import base64
import binascii
import os
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4
import pandas as pd
from monitoring import save_photo, analyze_frame
from scoring import calculate_integrity_score
from ai_report_agent import generate_integrity_report

import cv2
import numpy as np
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


app = Flask(__name__)
app.secret_key = "change-this-secret-key-before-deployment"

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "examguard.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024


def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_tables():
    connection = get_db()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            photo_filename TEXT
        )
    """)

    columns = [
        column["name"]
        for column in connection.execute(
            "PRAGMA table_info(candidates)"
        ).fetchall()
    ]

    if "photo_filename" not in columns:
        connection.execute(
            "ALTER TABLE candidates ADD COLUMN photo_filename TEXT"
        )

    connection.execute("""
        CREATE TABLE IF NOT EXISTS exam_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            exam_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'in_progress',
            started_at TEXT NOT NULL,
            submitted_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (candidate_id) REFERENCES candidates(id)
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS session_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            event_timestamp TEXT NOT NULL,
            details TEXT,
            duration_seconds REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES exam_sessions(id)
        )
    """)

    event_columns = {
        column["name"]
        for column in connection.execute(
            "PRAGMA table_info(session_events)"
        ).fetchall()
    }
    if "duration_seconds" not in event_columns:
        connection.execute(
            "ALTER TABLE session_events "
            "ADD COLUMN duration_seconds REAL NOT NULL DEFAULT 0"
        )

    connection.execute("""
        CREATE TABLE IF NOT EXISTS session_integrity_reports (
            session_id INTEGER PRIMARY KEY,
            integrity_score REAL NOT NULL,
            risk_label TEXT NOT NULL,
            face_presence_ratio REAL NOT NULL,
            event_penalty REAL NOT NULL,
            presence_penalty REAL NOT NULL,
            face_absent_duration REAL NOT NULL,
            report_text TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES exam_sessions(id)
        )
    """)

    # Keep administrator dashboard session/event queries efficient as the
    # monitoring log grows.
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_events_session_time "
        "ON session_events(session_id, event_timestamp)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_exam_sessions_status "
        "ON exam_sessions(status)"
    )

    connection.commit()
    connection.close()


def generate_session_report(connection, exam_session, submitted_at):
    """Score and summarise one candidate's completed exam session."""
    event_rows = connection.execute(
        """
        SELECT id, session_id, event_type, event_timestamp, details, duration_seconds
        FROM session_events
        WHERE session_id = ?
        ORDER BY event_timestamp
        """,
        (exam_session["id"],),
    ).fetchall()
    event_df = pd.DataFrame([dict(row) for row in event_rows])

    # If the candidate submits while their face is absent, the browser has no
    # later "face detected" frame to close that interval. Close it at
    # submission so the final score includes the full absence.
    if not event_df.empty:
        submitted_at_time = pd.to_datetime(submitted_at, errors="coerce")
        open_absences = event_df[
            (event_df["event_type"] == "no_face")
            & (event_df["duration_seconds"].fillna(0) <= 0)
        ]
        for row_index, row in open_absences.iterrows():
            absence_start = pd.to_datetime(row["event_timestamp"], errors="coerce")
            if pd.notna(submitted_at_time) and pd.notna(absence_start):
                duration = max(
                    0.0,
                    (submitted_at_time - absence_start).total_seconds(),
                )
                event_df.at[row_index, "duration_seconds"] = duration
                connection.execute(
                    "UPDATE session_events SET duration_seconds = ?, details = ? "
                    "WHERE id = ?",
                    (
                        duration,
                        f"Face was absent for {int(duration)} seconds.",
                        row["id"],
                    ),
                )

    score = calculate_integrity_score(
        event_df,
        exam_start=exam_session["started_at"],
        exam_end=submitted_at,
    )

    # These names match the live event values, with aliases retained for
    # generated data imported from the Week 1/2 exercise.
    event_types = event_df.get("event_type", pd.Series(dtype="object"))
    report_data = {
        "session_id": exam_session["id"],
        "integrity_score": score["integrity_score"],
        "risk_label": score["risk_label"],
        "tab_switch_count": int((event_types == "tab_switch").sum()),
        "focus_lost_count": int(
            event_types.isin(["window_focus_lost", "focus_lost"]).sum()
        ),
        "face_absent_count": int(
            event_types.isin(["no_face", "face_absent"]).sum()
        ),
        "face_absent_duration": score["face_absent_duration"],
    }
    report_text = generate_integrity_report(report_data)

    connection.execute(
        """
        INSERT INTO session_integrity_reports (
            session_id, integrity_score, risk_label, face_presence_ratio,
            event_penalty, presence_penalty, face_absent_duration, report_text,
            generated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            integrity_score = excluded.integrity_score,
            risk_label = excluded.risk_label,
            face_presence_ratio = excluded.face_presence_ratio,
            event_penalty = excluded.event_penalty,
            presence_penalty = excluded.presence_penalty,
            face_absent_duration = excluded.face_absent_duration,
            report_text = excluded.report_text,
            generated_at = excluded.generated_at
        """,
        (
            exam_session["id"], score["integrity_score"], score["risk_label"],
            score["face_presence_ratio"], score["event_penalty"],
            score["presence_penalty"], score["face_absent_duration"],
            report_text, submitted_at,
        ),
    )
    return {**score, "report_text": report_text, **report_data}


def build_analytics_data(event_rows, integrity_score):
    """Prepare the three candidate-level charts for the analytics page."""
    labels = {
        "tab_switch": "Tab switch",
        "window_focus_lost": "Focus lost",
        "no_face": "Face absent",
        "multiple_faces": "Multiple faces",
    }
    penalties = {
        "tab_switch": 5,
        "window_focus_lost": 3,
        "no_face": 5,
        "multiple_faces": 5,
    }
    event_counts = {label: 0 for label in labels.values()}
    timeline = []
    running_score = 100.0

    for event in event_rows:
        event_type = event["event_type"]
        if event_type not in labels:
            continue

        event_counts[labels[event_type]] += 1
        running_score = max(0, running_score - penalties[event_type])
        timeline.append({
            "label": datetime.fromisoformat(
                event["event_timestamp"]
            ).strftime("%H:%M:%S"),
            "score": round(running_score, 2),
        })

    if timeline:
        # The final point is the complete Pandas score, including the face
        # presence-ratio penalty calculated at submission.
        timeline[-1]["score"] = integrity_score
    else:
        timeline = [{"label": "Submitted", "score": integrity_score}]

    return {
        "events": [dict(event) for event in event_rows],
        "event_counts": event_counts,
        "score_timeline": timeline,
    }




def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )




# ============================================================
# SUSPICIOUS EVENT RULE ENGINE
# ============================================================

SUSPICIOUS_THRESHOLDS = {
    "tab_switches": 3,
    "focus_losses": 3,
    "face_absence_seconds": 60
}


def check_suspicious_events(connection, session_id):
    """
    Check the current exam session against the configured
    suspicious-event thresholds.

    Returns a list of suspicious events.
    """

    suspicious_events = []

    # --------------------------------------------------------
    # Count tab switches
    # --------------------------------------------------------

    tab_switch_result = connection.execute(
        """
        SELECT COUNT(*) AS total
        FROM session_events
        WHERE session_id = ?
          AND event_type = 'tab_switch'
        """,
        (session_id,)
    ).fetchone()

    tab_switch_count = tab_switch_result["total"]

    if tab_switch_count > SUSPICIOUS_THRESHOLDS["tab_switches"]:
        suspicious_events.append({
            "type": "excessive_tab_switches",
            "message": (
                f"Tab switch threshold exceeded: "
                f"{tab_switch_count} tab switches detected."
            ),
            "count": tab_switch_count
        })

    # --------------------------------------------------------
    # Count focus losses
    # --------------------------------------------------------

    focus_loss_result = connection.execute(
        """
        SELECT COUNT(*) AS total
        FROM session_events
        WHERE session_id = ?
          AND event_type = 'window_focus_lost'
        """,
        (session_id,)
    ).fetchone()

    focus_loss_count = focus_loss_result["total"]

    if focus_loss_count > SUSPICIOUS_THRESHOLDS["focus_losses"]:
        suspicious_events.append({
            "type": "excessive_focus_loss",
            "message": (
                f"Focus-loss threshold exceeded: "
                f"{focus_loss_count} focus-loss events detected."
            ),
            "count": focus_loss_count
        })

    # --------------------------------------------------------
    # Check face-absence intervals
    # --------------------------------------------------------

    face_absence_events = connection.execute(
        """
        SELECT id, details
        FROM session_events
        WHERE session_id = ?
          AND event_type = 'no_face'
        ORDER BY id DESC
        """,
        (session_id,)
    ).fetchall()

    for event in face_absence_events:

        details = event["details"] or ""

        # Example details:
        # "Face was absent for 135 seconds."

        if "Face was absent for" in details:

            try:
                duration_text = (
                    details
                    .replace("Face was absent for", "")
                    .replace("seconds.", "")
                    .strip()
                )

                absence_seconds = int(duration_text)

            except ValueError:
                continue

            if (
                absence_seconds
                > SUSPICIOUS_THRESHOLDS["face_absence_seconds"]
            ):
                suspicious_events.append({
                    "type": "long_face_absence",
                    "message": (
                        f"Face was absent for "
                        f"{absence_seconds} seconds."
                    ),
                    "duration": absence_seconds,
                    "event_id": event["id"]
                })

    return suspicious_events







@app.route("/")
def home():
    if "candidate_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))






@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not full_name or not email or not password:
            flash("Please fill in all required fields.", "error")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "error")
            return redirect(url_for("register"))

        connection = get_db()

        try:
            connection.execute(
                """
                INSERT INTO candidates (full_name, email, password, photo_filename)
                VALUES (?, ?, ?, ?)
                """,
                (full_name, email, generate_password_hash(password), None)
            )
            connection.commit()

            flash("Registration successful. Please sign in.", "success")
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash("This email is already registered.", "error")
            return redirect(url_for("register"))

        finally:
            connection.close()

    return render_template("register.html")






@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        connection = get_db()
        candidate = connection.execute(
            "SELECT * FROM candidates WHERE email = ?",
            (email,)
        ).fetchone()
        connection.close()

        if candidate and check_password_hash(candidate["password"], password):
            session.clear()
            session["candidate_id"] = candidate["id"]
            session["candidate_name"] = candidate["full_name"]
            session["photo_filename"] = candidate["photo_filename"]

            if not candidate["photo_filename"]:
                return redirect(url_for("capture_photo"))

            flash("Welcome back!", "success")
            return redirect(url_for("dashboard"))

        flash("Incorrect email or password.", "error")

    return render_template("login.html")





@app.route("/capture-photo", methods=["GET", "POST"])
def capture_photo():
    if "candidate_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        photo = request.files.get("photo")
        captured_photo = request.form.get("captured_photo", "")

        try:
            photo_filename, error_message = save_photo(
                photo,
                captured_photo,
                app.config["UPLOAD_FOLDER"],
            )

            if not photo_filename:
                raise ValueError(
                    error_message
                    or "Please capture or upload a registration photo."
                )

        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("capture_photo"))

        connection = get_db()

        connection.execute(
            "UPDATE candidates SET photo_filename = ? WHERE id = ?",
            (
                photo_filename,
                session["candidate_id"]
            )
        )

        connection.commit()
        connection.close()

        session["photo_filename"] = photo_filename

        flash("Photo saved successfully.", "success")

        return redirect(url_for("dashboard"))

    return render_template("capture_photo.html")





@app.route("/dashboard")
def dashboard():
    if "candidate_id" not in session:
        flash("Please sign in first.", "error")
        return redirect(url_for("login"))

    if not session.get("photo_filename"):
        return redirect(url_for("capture_photo"))

    return render_template("dashboard.html")





@app.route("/instructions")
def instructions():
    if "candidate_id" not in session:
        return redirect(url_for("login"))

    if not session.get("photo_filename"):
        return redirect(url_for("capture_photo"))

    return render_template("instructions.html")





@app.route("/start-exam", methods=["POST"])
def start_exam():
    if "candidate_id" not in session:
        return redirect(url_for("login"))

    return redirect(url_for("system_check"))



@app.route("/system-check")
def system_check():
    if "candidate_id" not in session:
        return redirect(url_for("login"))

    connection = get_db()

    candidate = connection.execute(
        "SELECT * FROM candidates WHERE id = ?",
        (session["candidate_id"],)
    ).fetchone()

    connection.close()

    if not candidate:
        session.clear()
        return redirect(url_for("login"))

    if not candidate["photo_filename"]:
        return redirect(url_for("capture_photo"))

    return render_template("system_check.html")




@app.route("/declaration", methods=["GET", "POST"])
def declaration():
    if "candidate_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        if not request.form.get("agree"):
            return render_template("declaration.html")

        connection = get_db()

        # Check whether the candidate already has an active exam
        active_exam = connection.execute(
            """
            SELECT * FROM exam_sessions
            WHERE candidate_id = ? AND status = 'in_progress'
            ORDER BY id DESC
            LIMIT 1
            """,
            (session["candidate_id"],)
        ).fetchone()

        if active_exam:
            connection.close()
            return redirect(
                url_for("exam", session_id=active_exam["id"])
            )

        # Create a new exam session
        current_time = datetime.now(timezone.utc).isoformat()

        cursor = connection.execute(
            """
            INSERT INTO exam_sessions (
                candidate_id, exam_name, status, started_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                session["candidate_id"],
                "Python Fundamentals Examination",
                "in_progress",
                current_time
            )
        )

        connection.commit()

        exam_id = cursor.lastrowid

        connection.close()

        return redirect(
            url_for("exam", session_id=exam_id)
        )

    return render_template("declaration.html")







@app.route("/exam/<int:session_id>")
def exam(session_id):
    if "candidate_id" not in session:
        return redirect(url_for("login"))

    connection = get_db()

    exam_session = connection.execute(
        """
        SELECT * FROM exam_sessions
        WHERE id = ? AND candidate_id = ?
        """,
        (session_id, session["candidate_id"])
    ).fetchone()

    connection.close()

    if exam_session is None:
        flash("Exam was not found.", "error")
        return redirect(url_for("dashboard"))

    if exam_session["status"] != "in_progress":
        flash("This exam is not active.", "error")
        return redirect(url_for("dashboard"))

    return render_template("exam.html", exam_session=exam_session)





@app.route("/exam/<int:session_id>/submit", methods=["POST"])
def submit_exam(session_id):
    if "candidate_id" not in session:
        return redirect(url_for("login"))

    connection = get_db()

    exam_session = connection.execute(
        """
        SELECT * FROM exam_sessions
        WHERE id = ? AND candidate_id = ? AND status = 'in_progress'
        """,
        (session_id, session["candidate_id"])
    ).fetchone()

    if exam_session is None:
        connection.close()
        flash("Active exam was not found.", "error")
        return redirect(url_for("dashboard"))

    

    submitted_time = datetime.now(timezone.utc).isoformat()

    connection.execute(
        """
        UPDATE exam_sessions
        SET status = ?, submitted_at = ?
        WHERE id = ?
        """,
        (
            "submitted",
            submitted_time,
            session_id,
        ),
    )

    integrity_report = generate_session_report(
        connection,
        exam_session,
        submitted_time,
    )

    connection.commit()
    connection.close()

    return render_template(
        "submission_success.html",
        exam_name=exam_session["exam_name"],
        submitted_at=submitted_time,
        session_id=session_id,
    )


@app.route("/analytics/<int:session_id>")
def view_analytics(session_id):
    """Show the completed session analytics to its own candidate only."""
    if "candidate_id" not in session:
        return redirect(url_for("login"))

    connection = get_db()
    exam_session = connection.execute(
        """
        SELECT id, exam_name, status
        FROM exam_sessions
        WHERE id = ? AND candidate_id = ? AND status = 'submitted'
        """,
        (session_id, session["candidate_id"]),
    ).fetchone()

    if exam_session is None:
        connection.close()
        flash("Analytics are available only after your exam is submitted.", "error")
        return redirect(url_for("dashboard"))

    integrity_report = connection.execute(
        "SELECT * FROM session_integrity_reports WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    event_rows = connection.execute(
        """
        SELECT event_type, event_timestamp, details, duration_seconds
        FROM session_events
        WHERE session_id = ?
        ORDER BY event_timestamp
        LIMIT 100
        """,
        (session_id,),
    ).fetchall()
    connection.close()

    if integrity_report is None:
        flash("The integrity report is still being prepared.", "error")
        return redirect(url_for("dashboard"))

    analytics_data = build_analytics_data(
        event_rows,
        integrity_report["integrity_score"],
    )
    total_violations = sum(analytics_data["event_counts"].values())

    return render_template(
        "analytics.html",
        exam_session=exam_session,
        integrity_report=integrity_report,
        analytics_data=analytics_data,
        total_violations=total_violations,
    )




@app.route("/api/exam/<int:session_id>/face-status", methods=["POST"])
def analyze_face_frame(session_id):
    if "candidate_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True) or {}
    frame_data = data.get("frame", "")

    if not frame_data or "," not in frame_data:
        return jsonify({"error": "Invalid webcam frame"}), 400

    connection = get_db()

    active_exam = connection.execute(
        """
        SELECT id
        FROM exam_sessions
        WHERE id = ?
          AND candidate_id = ?
          AND status = 'in_progress'
        """,
        (session_id, session["candidate_id"])
    ).fetchone()

    if active_exam is None:
        connection.close()
        return jsonify({"error": "Active exam not found"}), 404

    try:
        # Analyze webcam frame using Haar Cascade
        result = analyze_frame(frame_data)

        event_type = result["event_type"]
        status_label = result["status_label"]
        details = result["details"]
        face_count = result["face_count"]
        face_boxes = result["face_boxes"]

        # Get the previous face-related event
        previous_face_event = connection.execute(
            """
            SELECT id, event_type, event_timestamp, details
            FROM session_events
            WHERE session_id = ?
              AND event_type IN (
                  'no_face',
                  'face_detected',
                  'multiple_faces'
              )
            ORDER BY id DESC
            LIMIT 1
            """,
            (session_id,)
        ).fetchone()

        current_time = datetime.now(timezone.utc)
        current_timestamp = current_time.isoformat()

        # Details that will be sent back to exam.html
        event_details = details

        # -------------------------------------------------
        # FACE HAS RETURNED AFTER BEING ABSENT
        # -------------------------------------------------
        if (
            previous_face_event is not None
            and previous_face_event["event_type"] == "no_face"
            and event_type in ("face_detected", "multiple_faces")
        ):
            absence_start = datetime.fromisoformat(
                previous_face_event["event_timestamp"]
            )

            absence_duration = (
                current_time - absence_start
            ).total_seconds()

            absence_seconds = int(absence_duration)

            event_details = (
                f"Face was absent for {absence_seconds} seconds."
            )

            # Update the original no-face event
            connection.execute(
                """
                UPDATE session_events
                SET details = ?, duration_seconds = ?
                WHERE id = ?
                """,
                (
                    event_details,
                    absence_seconds,
                    previous_face_event["id"]
                )
            )

        # -------------------------------------------------
        # SAVE NEW FACE STATUS ONLY WHEN STATUS CHANGES
        # -------------------------------------------------
        if (
            previous_face_event is None
            or previous_face_event["event_type"] != event_type
        ):
            connection.execute(
                """
                INSERT INTO session_events (
                    session_id,
                    event_type,
                    event_timestamp,
                    details,
                    duration_seconds
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    event_type,
                    current_timestamp,
                    event_details,
                    0,
                )
            )

            connection.commit()

        connection.close()

        # Send details to exam.html
        return jsonify({
            "status": event_type,
            "label": status_label,
            "details": event_details,
            "face_count": face_count,
            "faces": face_boxes
        })

    except ValueError as error:
        connection.close()
        return jsonify({"error": str(error)}), 400

    except Exception as error:
        connection.close()
        return jsonify({"error": str(error)}), 500





@app.route("/api/exam/<int:session_id>/event", methods=["POST"])
def log_exam_event(session_id):
    if "candidate_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True) or {}

    event_type = data.get("event_type", "")
    details = data.get("details", "")

    allowed_events = {
        "tab_switch",
        "window_focus_lost",
        "window_focus_returned"
    }

    if event_type not in allowed_events:
        return jsonify({"error": "Invalid event"}), 400

    connection = get_db()

    active_exam = connection.execute(
        """
        SELECT id
        FROM exam_sessions
        WHERE id = ?
          AND candidate_id = ?
          AND status = 'in_progress'
        """,
        (session_id, session["candidate_id"])
    ).fetchone()

    if active_exam is None:
        connection.close()
        return jsonify({"error": "Active exam not found"}), 404

    try:
        # -------------------------------------------------
        # SAVE BROWSER EVENT
        # -------------------------------------------------

        connection.execute(
            """
            INSERT INTO session_events (
                session_id,
                event_type,
                event_timestamp,
                details,
                duration_seconds
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_id,
                event_type,
                datetime.now(timezone.utc).isoformat(),
                details,
                0,
            )
        )

        connection.commit()

        # -------------------------------------------------
        # CHECK SUSPICIOUS EVENT RULES
        # -------------------------------------------------

        suspicious_events = check_suspicious_events(
            connection,
            session_id
        )

        connection.close()

        return jsonify({
            "success": True,
            "suspicious": len(suspicious_events) > 0,
            "suspicious_events": suspicious_events
        })

    except Exception as error:
        connection.close()

        return jsonify({
            "error": str(error)
        }), 500






    


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("login"))


if __name__ == "__main__":
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    create_tables()
    app.run(debug=True)
