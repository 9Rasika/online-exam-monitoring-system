import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from faker import Faker


# ============================================================
# CONFIGURATION
# ============================================================

fake = Faker()

Faker.seed(42)
random.seed(42)

OUTPUT_FILE = Path("data/synthetic_session_logs.csv")

TOTAL_SESSIONS = 100


# ============================================================
# NORMAL EVENTS
# ============================================================

NORMAL_EVENTS = [
    ("answer_saved", "Low"),
    ("session_paused", "Low"),
    ("session_resumed", "Low")
]


# ============================================================
# SUSPICIOUS EVENTS
# ============================================================

SUSPICIOUS_EVENTS = [
    ("tab_switch", "Medium"),
    ("focus_lost", "Medium"),
    ("face_absent", "High")
]


# ============================================================
# GENERATE ONE SESSION
# ============================================================

def create_session(session_number):

    session_id = f"SESSION-{session_number:04d}"

    candidate_name = fake.name()
    candidate_email = fake.unique.email()

    exam_name = "Online Programming Examination"

    start_time = (
        datetime.now(timezone.utc)
        - timedelta(
            days=random.randint(1, 30),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59)
        )
    )

    current_time = start_time

    rows = []

    # --------------------------------------------------------
    # SESSION START
    # --------------------------------------------------------

    rows.append({
        "session_id": session_id,
        "candidate_name": candidate_name,
        "candidate_email": candidate_email,
        "exam_name": exam_name,
        "event_type": "session_started",
        "event_timestamp": current_time.isoformat(),
        "duration_seconds": 0,
        "severity": "Low"
    })


    # ========================================================
    # RANDOMLY SELECT BEHAVIOR PROFILE
    # ========================================================

    profile = random.choices(
        ["Low", "Medium", "High"],
        weights=[45, 35, 20],
        k=1
    )[0]


    # ========================================================
    # LOW-RISK PROFILE
    # ========================================================

    if profile == "Low":

        # Mostly normal activity
        normal_events = random.randint(8, 14)

        suspicious_events = random.randint(0, 2)


    # ========================================================
    # MEDIUM-RISK PROFILE
    # ========================================================

    elif profile == "Medium":

        normal_events = random.randint(6, 10)

        suspicious_events = random.randint(3, 6)


    # ========================================================
    # HIGH-RISK PROFILE
    # ========================================================

    else:

        normal_events = random.randint(4, 8)

        suspicious_events = random.randint(6, 10)


    # ========================================================
    # CREATE EVENT COUNT
    # ========================================================

    total_events = normal_events + suspicious_events

    event_list = []

    # Add normal events
    for _ in range(normal_events):

        event_type, severity = random.choice(
            NORMAL_EVENTS
        )

        event_list.append(
            (event_type, severity)
        )


    # Add suspicious events
    for _ in range(suspicious_events):

        event_type, severity = random.choice(
            SUSPICIOUS_EVENTS
        )

        event_list.append(
            (event_type, severity)
        )


    # Shuffle so events are not grouped
    random.shuffle(event_list)


    # ========================================================
    # GENERATE EVENTS
    # ========================================================

    for event_type, severity in event_list:

        current_time += timedelta(
            seconds=random.randint(45, 180)
        )

        duration = 0

        # ----------------------------------------------------
        # FACE ABSENCE
        # ----------------------------------------------------

        if event_type == "face_absent":

            if profile == "Low":

                duration = random.randint(
                    5,
                    20
                )

            elif profile == "Medium":

                duration = random.randint(
                    20,
                    70
                )

            else:

                duration = random.randint(
                    60,
                    150
                )


        # ----------------------------------------------------
        # TAB SWITCH / FOCUS LOSS
        # ----------------------------------------------------

        elif event_type in (
            "tab_switch",
            "focus_lost"
        ):

            duration = 0


        # ----------------------------------------------------
        # NORMAL EVENTS
        # ----------------------------------------------------

        else:

            duration = 0


        rows.append({
            "session_id": session_id,
            "candidate_name": candidate_name,
            "candidate_email": candidate_email,
            "exam_name": exam_name,
            "event_type": event_type,
            "event_timestamp": current_time.isoformat(),
            "duration_seconds": duration,
            "severity": severity
        })


    # ========================================================
    # SESSION SUBMITTED
    # ========================================================

    current_time += timedelta(
        minutes=random.randint(2, 5)
    )

    rows.append({
        "session_id": session_id,
        "candidate_name": candidate_name,
        "candidate_email": candidate_email,
        "exam_name": exam_name,
        "event_type": "session_submitted",
        "event_timestamp": current_time.isoformat(),
        "duration_seconds": 0,
        "severity": "Low"
    })


    return rows


# ============================================================
# GENERATE ALL SESSIONS
# ============================================================

def generate_dataset():

    all_rows = []

    for session_number in range(
        1,
        TOTAL_SESSIONS + 1
    ):

        session_rows = create_session(
            session_number
        )

        all_rows.extend(
            session_rows
        )

    return all_rows


# ============================================================
# SAVE DATASET
# ============================================================

def save_dataset(rows):

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    fieldnames = [
        "session_id",
        "candidate_name",
        "candidate_email",
        "exam_name",
        "event_type",
        "event_timestamp",
        "duration_seconds",
        "severity"
    ]

    with OUTPUT_FILE.open(
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        writer.writeheader()

        writer.writerows(rows)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    rows = generate_dataset()

    save_dataset(rows)

    print()
    print("=" * 60)
    print("Synthetic Session Log Generation Complete")
    print("=" * 60)
    print(f"Sessions generated : {TOTAL_SESSIONS}")
    print(f"Event rows         : {len(rows)}")
    print(f"Output file        : {OUTPUT_FILE}")
    print("=" * 60)