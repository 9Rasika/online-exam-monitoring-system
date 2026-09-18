import pandas as pd
import re


# ============================================================
# EVENT WEIGHTS
# ============================================================

EVENT_WEIGHTS = {
    "tab_switch": 5,
    "window_focus_lost": 3,
    "no_face": 5,
    "multiple_faces": 5,
}

# The live Flask application and the synthetic-data exercises used slightly
# different names for the same events.  Normalising them here lets the scoring
# module work with both sources without silently ignoring a suspicious event.
EVENT_ALIASES = {
    "focus_lost": "window_focus_lost",
    "face_absent": "no_face",
}


# ============================================================
# RISK THRESHOLDS
# ============================================================

RISK_THRESHOLDS = {
    "low": 80,
    "medium": 50
}


# ============================================================
# RISK LABEL
# ============================================================

def get_risk_label(score):
    """
    Convert integrity score into a risk label.
    """

    if score >= RISK_THRESHOLDS["low"]:
        return "Low"

    if score >= RISK_THRESHOLDS["medium"]:
        return "Medium"

    return "High"


# ============================================================
# EXTRACT FACE ABSENCE DURATION
# ============================================================

def extract_face_absence_duration(details):
    """
    Extract face absence duration from the details field.

    Example:
        "Face was absent for 135 seconds."

    Returns:
        135.0
    """

    if not details:
        return 0.0

    match = re.search(
        r"absent\s+for\s+(\d+(?:\.\d+)?)\s*seconds?",
        str(details),
        re.IGNORECASE
    )

    if match:
        return float(match.group(1))

    return 0.0


def normalise_event_types(df):
    """Return a copy with historical event names mapped to live names."""
    normalised = df.copy()
    if "event_type" in normalised.columns:
        normalised["event_type"] = normalised["event_type"].replace(
            EVENT_ALIASES
        )
    return normalised


# ============================================================
# CALCULATE SINGLE SESSION SCORE
# ============================================================

def calculate_integrity_score(
    session_df,
    exam_start=None,
    exam_end=None
):
    """
    Calculate integrity score for one exam session.

    Parameters:
        session_df : DataFrame
            Events belonging to one session.

        exam_start : optional
            Actual exam start time from exam_sessions.started_at.

        exam_end : optional
            Actual exam submission time from exam_sessions.submitted_at.

    Returns:
        Dictionary containing:
            integrity_score
            risk_label
            face_presence_ratio
            event_penalty
            presence_penalty
            face_absent_duration
            exam_duration
    """

    # --------------------------------------------------------
    # Empty session
    # --------------------------------------------------------

    if session_df.empty:

        return {
            "integrity_score": 100.0,
            "risk_label": "Low",
            "face_presence_ratio": 1.0,
            "event_penalty": 0.0,
            "presence_penalty": 0.0,
            "face_absent_duration": 0.0,
            "exam_duration": 0.0
        }


    # --------------------------------------------------------
    # Make a copy
    # --------------------------------------------------------

    df = normalise_event_types(session_df)


    # --------------------------------------------------------
    # Make sure event_timestamp is datetime
    # --------------------------------------------------------

    if "event_timestamp" in df.columns:

        df["event_timestamp"] = pd.to_datetime(
            df["event_timestamp"],
            errors="coerce"
        )


    # --------------------------------------------------------
    # EVENT PENALTY
    # --------------------------------------------------------

    event_penalty = 0.0

    for event_type, weight in EVENT_WEIGHTS.items():

        event_count = (
            df["event_type"] == event_type
        ).sum()

        event_penalty += event_count * weight


    # --------------------------------------------------------
    # FACE ABSENCE DURATION
    # --------------------------------------------------------

    face_absent_duration = 0.0

    no_face_events = df[
        df["event_type"] == "no_face"
    ]

    if not no_face_events.empty:

        for _, row in no_face_events.iterrows():

            # SQLite events record the completed interval in ``details``;
            # generated CSV data keeps it in ``duration_seconds``.
            duration = row.get("duration_seconds", 0)
            if pd.isna(duration) or float(duration) <= 0:
                duration = extract_face_absence_duration(
                    row.get("details", "")
                )

            face_absent_duration += float(duration)


    # --------------------------------------------------------
    # EXAM START AND END TIME
    # --------------------------------------------------------

    total_exam_seconds = 0.0

    # Use actual exam session times if available.
    if exam_start is not None and exam_end is not None:

        start_time = pd.to_datetime(
            exam_start,
            errors="coerce"
        )

        end_time = pd.to_datetime(
            exam_end,
            errors="coerce"
        )

        if pd.notna(start_time) and pd.notna(end_time):

            total_exam_seconds = (
                end_time - start_time
            ).total_seconds()


    # --------------------------------------------------------
    # FALLBACK
    # --------------------------------------------------------
    # If exam start/end are not supplied, use event timestamps.
    # This keeps the function compatible with analytics.py.
    # --------------------------------------------------------

    if total_exam_seconds <= 0:

        if "event_timestamp" in df.columns:

            valid_times = df[
                "event_timestamp"
            ].dropna()

            if len(valid_times) >= 2:

                start_time = valid_times.min()
                end_time = valid_times.max()

                total_exam_seconds = (
                    end_time - start_time
                ).total_seconds()


    # --------------------------------------------------------
    # FACE PRESENCE RATIO
    # --------------------------------------------------------

    if total_exam_seconds > 0:

        face_presence_ratio = (
            1 -
            (
                face_absent_duration /
                total_exam_seconds
            )
        )

        # Keep value between 0 and 1.
        face_presence_ratio = max(
            0.0,
            min(1.0, face_presence_ratio)
        )

    else:

        face_presence_ratio = 1.0


    # --------------------------------------------------------
    # PRESENCE PENALTY
    # --------------------------------------------------------

    presence_penalty = (
        (1 - face_presence_ratio) * 30
    )


    # --------------------------------------------------------
    # FINAL SCORE
    # --------------------------------------------------------

    raw_score = (
        100
        - event_penalty
        - presence_penalty
    )


    # Keep score between 0 and 100.
    integrity_score = max(
        0.0,
        min(100.0, raw_score)
    )

    integrity_score = round(
        integrity_score,
        2
    )


    # --------------------------------------------------------
    # RISK LABEL
    # --------------------------------------------------------

    risk_label = get_risk_label(
        integrity_score
    )


    # --------------------------------------------------------
    # RETURN RESULTS
    # --------------------------------------------------------

    return {
        "integrity_score": integrity_score,
        "risk_label": risk_label,
        "face_presence_ratio": round(
            face_presence_ratio,
            4
        ),
        "event_penalty": round(
            event_penalty,
            2
        ),
        "presence_penalty": round(
            presence_penalty,
            2
        ),
        "face_absent_duration": round(
            face_absent_duration,
            2
        ),
        "exam_duration": round(
            total_exam_seconds,
            2
        )
    }


# ============================================================
# CALCULATE ALL SESSION SCORES
# ============================================================

def calculate_all_session_scores(df):
    """
    Calculate integrity scores for all sessions
    contained in the DataFrame.

    Expected columns:

        session_id
        event_type
        event_timestamp
        details
    """

    results = []


    # --------------------------------------------------------
    # Empty dataset
    # --------------------------------------------------------

    if df.empty:

        return pd.DataFrame(
            columns=[
                "session_id",
                "integrity_score",
                "risk_label",
                "face_presence_ratio",
                "event_penalty",
                "presence_penalty",
                "face_absent_duration",
                "exam_duration"
            ]
        )


    # --------------------------------------------------------
    # Group events by session
    # --------------------------------------------------------

    for session_id, session_df in df.groupby(
        "session_id"
    ):

        score = calculate_integrity_score(
            session_df
        )

        score["session_id"] = session_id

        results.append(score)


    # --------------------------------------------------------
    # Convert results to DataFrame
    # --------------------------------------------------------

    return pd.DataFrame(results)


# ============================================================
# MAIN TEST
# ============================================================

if __name__ == "__main__":

    csv_file = "data/synthetic_session_logs.csv"

    try:

        df = pd.read_csv(csv_file)

        results = calculate_all_session_scores(df)

        print()
        print("Integrity Scoring Results")
        print("=" * 80)

        print(
            results.to_string(
                index=False
            )
        )

    except FileNotFoundError:

        print(
            f"Error: {csv_file} was not found."
        )

    except Exception as e:

        print(
            f"Error while calculating scores: {e}"
        )
