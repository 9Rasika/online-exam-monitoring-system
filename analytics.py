"""Create simple, presentation-ready charts from the live Exam Monitoring DB.

Run ``python analytics.py``.  PNG files are saved in ``data/charts`` and the
live session cluster CSV is refreshed in ``data/session_clusters.csv``.
"""

import os

import matplotlib.pyplot as plt

from dashboard_data import prepare_dashboard_data


OUTPUT_FILE = "data/session_clusters.csv"
CHART_DIR = "data/charts"


def export_session_clusters(sessions, output_file=OUTPUT_FILE):
    """Save the easy-to-read cluster assignment table for each session."""
    columns = [
        "session_id", "candidate_name", "exam_name", "status",
        "integrity_score", "risk_label", "cluster", "behavioural_risk_cluster",
    ]
    clusters = sessions.reindex(columns=columns)
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    clusters.to_csv(output_file, index=False)
    return clusters


def save_simple_charts(sessions, events, chart_dir=CHART_DIR):
    """Save four charts that are straightforward to explain in a demo."""
    os.makedirs(chart_dir, exist_ok=True)
    plt.style.use("seaborn-v0_8-whitegrid")

    # 1. Integrity score for every session.
    ordered = sessions.sort_values("session_id")
    colors = ordered["risk_label"].map({"Low": "#22a06b", "Medium": "#e6a700", "High": "#d14343"}).fillna("#789")
    figure, axis = plt.subplots(figsize=(10, 5))
    axis.bar(ordered["session_id"].astype(str), ordered["integrity_score"], color=colors)
    axis.axhline(80, color="#22a06b", linestyle="--", linewidth=1, label="Low-risk threshold")
    axis.axhline(50, color="#e6a700", linestyle="--", linewidth=1, label="Medium-risk threshold")
    axis.set(title="Integrity Score by Session", xlabel="Session ID", ylabel="Integrity score (%)", ylim=(0, 105))
    axis.legend()
    figure.tight_layout()
    figure.savefig(os.path.join(chart_dir, "integrity_scores.png"), dpi=160)
    plt.close(figure)

    # 2. Risk-level share: a simple answer to "how many need review?".
    risk_counts = sessions["risk_label"].value_counts().reindex(["Low", "Medium", "High"]).dropna()
    if not risk_counts.empty:
        figure, axis = plt.subplots(figsize=(7, 5))
        axis.pie(risk_counts, labels=risk_counts.index, autopct="%1.0f%%", startangle=90,
                 colors=["#22a06b", "#e6a700", "#d14343"][:len(risk_counts)])
        axis.set_title("Session Risk-Level Distribution")
        figure.tight_layout()
        figure.savefig(os.path.join(chart_dir, "risk_distribution.png"), dpi=160)
        plt.close(figure)

    # 3. Which monitoring event happened most often?
    if not events.empty:
        event_counts = events["event_type"].str.replace("_", " ").str.title().value_counts()
        figure, axis = plt.subplots(figsize=(9, 5))
        axis.bar(event_counts.index, event_counts.values, color="#3b82f6")
        axis.set(title="Monitoring Event Frequency", xlabel="Event type", ylabel="Number of events")
        axis.tick_params(axis="x", rotation=25)
        figure.tight_layout()
        figure.savefig(os.path.join(chart_dir, "event_frequency.png"), dpi=160)
        plt.close(figure)

    # 4. Simple count of the automatically produced risk groups.
    cluster_counts = sessions["behavioural_risk_cluster"].value_counts().reindex(["Low", "Medium", "High"]).dropna()
    if not cluster_counts.empty:
        figure, axis = plt.subplots(figsize=(7, 5))
        axis.bar(cluster_counts.index, cluster_counts.values, color=["#22a06b", "#e6a700", "#d14343"][:len(cluster_counts)])
        axis.set(title="Behavioural Risk Clusters", xlabel="Risk cluster", ylabel="Number of sessions")
        figure.tight_layout()
        figure.savefig(os.path.join(chart_dir, "risk_clusters.png"), dpi=160)
        plt.close(figure)


def run_analytics():
    """Refresh exports and chart images from the current live database."""
    data = prepare_dashboard_data()
    clusters = export_session_clusters(data["sessions"])
    save_simple_charts(data["sessions"], data["events"])
    return len(clusters), len(data["events"])


if __name__ == "__main__":
    session_count, event_count = run_analytics()
    print(f"Created simple charts for {session_count} sessions and {event_count} monitoring events in {CHART_DIR}.")
