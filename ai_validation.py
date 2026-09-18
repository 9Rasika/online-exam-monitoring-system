import re


# ============================================================
# VALIDATE AI INTEGRITY REPORT
# ============================================================

def validate_ai_report(session_data, report):

    validation_results = {}

    # --------------------------------------------------------
    # 1. CHECK INTEGRITY SCORE
    # --------------------------------------------------------

    expected_score = str(
        round(float(session_data["integrity_score"]), 2)
    )

    score_found = expected_score in report

    validation_results["score_correct"] = score_found

    # --------------------------------------------------------
    # 2. CHECK RISK LABEL
    # --------------------------------------------------------

    expected_risk = session_data["risk_label"]

    risk_found = expected_risk.lower() in report.lower()

    validation_results["risk_label_correct"] = risk_found

    # --------------------------------------------------------
    # 3. CHECK TAB SWITCH INFORMATION
    # --------------------------------------------------------

    tab_count = int(
        session_data["tab_switch_count"]
    )

    if tab_count == 0:

        tab_valid = not bool(
            re.search(
                r"\b(tab switch|tab switching|switched tabs)\b",
                report,
                re.IGNORECASE
            )
        )

    else:

        tab_valid = bool(
            re.search(
                r"tab",
                report,
                re.IGNORECASE
            )
        )

    validation_results["tab_switch_information"] = tab_valid

    # --------------------------------------------------------
    # 4. CHECK FOCUS LOSS INFORMATION
    # --------------------------------------------------------

    focus_count = int(
        session_data["focus_lost_count"]
    )

    if focus_count == 0:

        focus_valid = not bool(
            re.search(
                r"\b(focus loss|lost focus)\b",
                report,
                re.IGNORECASE
            )
        )

    else:

        focus_valid = bool(
            re.search(
                r"focus",
                report,
                re.IGNORECASE
            )
        )

    validation_results["focus_loss_information"] = focus_valid

    # --------------------------------------------------------
    # 5. CHECK FACE ABSENCE INFORMATION
    # --------------------------------------------------------

    face_count = int(
        session_data["face_absent_count"]
    )

    if face_count == 0:

        face_valid = not bool(
            re.search(
                r"\b(face absence|face was absent|face not detected)\b",
                report,
                re.IGNORECASE
            )
        )

    else:

        face_valid = bool(
            re.search(
                r"face",
                report,
                re.IGNORECASE
            )
        )

    validation_results["face_absence_information"] = face_valid

    # --------------------------------------------------------
    # 6. OVERALL VALIDATION
    # --------------------------------------------------------

    validation_results["overall_valid"] = all(
        validation_results.values()
    )

    return validation_results


# ============================================================
# DISPLAY VALIDATION
# ============================================================

def print_validation_results(results):

    print()
    print("=" * 70)
    print("AI SUMMARY VALIDATION")
    print("=" * 70)

    for check, result in results.items():

        if check == "overall_valid":
            continue

        status = "PASS" if result else "FAIL"

        print(
            f"{check:<35} : {status}"
        )

    print("-" * 70)

    if results["overall_valid"]:
        print("FINAL RESULT : PASS")
        print("AI summary is consistent with the session data.")

    else:
        print("FINAL RESULT : FAIL")
        print("AI summary requires manual review.")