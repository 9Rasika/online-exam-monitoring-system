"""Generate a factual integrity report for one completed exam session.

The Flask application can always use this module. Gemini/LangChain is used
when it is configured, while a deterministic report keeps exam submission
reliable on machines without an API key or AI packages.
"""

import os

from ai_validation import validate_ai_report


def build_fallback_report(session_data):
    """Create a factual report directly from the session metrics."""
    tab_switches = int(session_data["tab_switch_count"])
    focus_losses = int(session_data["focus_lost_count"])
    face_absences = int(session_data["face_absent_count"])
    absence_seconds = round(float(session_data["face_absent_duration"]), 1)

    observations = []
    if tab_switches:
        observations.append(f"{tab_switches} tab switch(es) were recorded.")
    if focus_losses:
        observations.append(f"{focus_losses} focus-loss event(s) were recorded.")
    if face_absences:
        observations.append(
            f"Face absence was recorded {face_absences} time(s), totalling "
            f"{absence_seconds:g} seconds."
        )
    if not observations:
        observations.append("No suspicious monitoring events were recorded.")

    return "\n".join([
        "Integrity Assessment:",
        f"Risk Level: {session_data['risk_label']}",
        f"Integrity Score: {float(session_data['integrity_score']):.2f}",
        "",
        "Key Observations:",
        *[f"- {observation}" for observation in observations],
        "",
        "Conclusion:",
        "This summary is based on the recorded monitoring events and should "
        "be reviewed by the invigilator alongside the session evidence.",
    ])


def generate_integrity_report(session_data):
    """Use Gemini when available; otherwise return a validated local report."""
    fallback_report = build_fallback_report(session_data)

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    # Keep the candidate submission path responsive. Set this explicitly in
    # .env when live Gemini summaries are wanted in addition to the local,
    # deterministic report.
    ai_enabled = os.getenv("ENABLE_AI_REPORTS", "false").lower() == "true"
    api_key = os.getenv("GEMINI_API_KEY")

    if not ai_enabled or not api_key:
        return fallback_report

    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_google_genai import ChatGoogleGenerativeAI

        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "Generate a concise, factual exam-integrity report using only "
                "the provided data. Do not invent events or alter the score or "
                "risk label. Mention only non-zero event types.",
            ),
            (
                "human",
                "Session ID: {session_id}\n"
                "Integrity Score: {integrity_score:.2f}\n"
                "Risk Level: {risk_label}\n"
                "Tab Switch Count: {tab_switch_count}\n"
                "Focus Loss Count: {focus_lost_count}\n"
                "Face Absence Count: {face_absent_count}\n"
                "Face Absence Duration: {face_absent_duration:.1f} seconds",
            ),
        ])
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
            google_api_key=api_key,
        )
        report = llm.invoke(prompt.format_messages(**session_data)).content

        # Never save an AI response that contradicts the calculated metrics.
        if validate_ai_report(session_data, report)["overall_valid"]:
            return report
    except Exception:
        # A report must not prevent the candidate from submitting an exam.
        pass

    return fallback_report
