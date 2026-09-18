"""Create evidence exports from the live ExamGuard database.

Run ``python alert_manager.py`` when a file copy of dashboard alerts is
needed for an offline review.
"""

import os

from dashboard_data import build_alerts, load_dashboard_data


OUTPUT_FILE = "data/alerts_evidence.csv"


def create_alerts_and_evidence(events):
    """Compatibility wrapper for the shared dashboard alert rules."""
    return build_alerts(events)


def save_alerts_and_evidence(evidence, output_file=OUTPUT_FILE):
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    evidence.to_csv(output_file, index=False)


if __name__ == "__main__":
    evidence = create_alerts_and_evidence(load_dashboard_data()["events"])
    save_alerts_and_evidence(evidence)
    print(f"Saved {len(evidence)} live alert/evidence records to {OUTPUT_FILE}")
