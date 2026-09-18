# Online Exam Monitoring & Integrity Analytics Platform

An online exam monitoring and integrity analytics platform designed to monitor candidate activity during examinations, detect suspicious behavior, calculate integrity scores, and generate analytical and AI-based integrity reports.

## Features

- Candidate registration and login
- Candidate photo capture and identity verification
- Browser system check before starting an exam
- Camera permission and camera accessibility check
- Real-time face presence monitoring using OpenCV Haar Cascade
- Detection of:
  - Face not detected
  - Multiple faces detected
  - Face detected
- Browser activity monitoring
- Tab-switch and window-focus-loss event logging
- Automatic integrity score calculation
- Risk classification based on integrity score
- Face-presence ratio analysis
- K-Means clustering for session risk analysis
- Data analytics using Pandas and visualization libraries
- AI-generated integrity reports using LangChain and Google Gemini
- Alert and evidence management
- Streamlit-based analytics dashboard
- Session data and integrity analysis stored using SQLite
- Automated testing for dashboard data processing

## Technology Stack

- **Backend:** Python, Flask
- **Database:** SQLite
- **Computer Vision:** OpenCV, Haar Cascade
- **Data Science:** Pandas, NumPy, Scikit-learn
- **Data Visualization:** Matplotlib, Seaborn
- **Machine Learning:** K-Means Clustering
- **AI:** LangChain, Google Gemini
- **Dashboard:** Streamlit
- **Frontend:** HTML, CSS, JavaScript
- **Testing:** Pytest

## How It Works

1. Candidate registers and provides a photograph.
2. The photograph is validated using Haar Cascade face detection.
3. The candidate logs in and accesses the dashboard.
4. Before starting the exam, the system checks browser compatibility, camera permission, and camera accessibility.
5. The candidate accepts the examination declaration.
6. The exam starts and monitoring begins.
7. The system monitors face presence and browser activity during the examination.
8. Monitoring events are stored in the SQLite database.
9. After submission, the system calculates an integrity score and risk level.
10. Data science analytics are performed on session data.
11. An AI-generated integrity report is created for the completed session.
12. The results can be viewed through the analytics dashboard.

## Face Monitoring

The project uses **OpenCV Haar Cascade** for face detection.

It does not perform face recognition or identify the candidate's identity from the camera feed.

During the examination, the system detects whether:

- One face is visible
- No face is visible
- Multiple faces are visible

These monitoring events are recorded as part of the examination integrity analysis.

## Integrity Analysis

The system considers different monitoring events and face-presence information when calculating the integrity score.

Examples of monitored events include:

- Tab switching
- Window focus loss
- Face absence

The resulting score is used to classify the session into a risk level.

## Data Science Analytics

The platform creates session-level features such as:

- Tab switch count
- Focus loss count
- Face absence count
- Face absence duration
- Integrity score

K-Means clustering is then used to group examination sessions according to their monitoring characteristics and integrity scores.

## AI Integrity Reports

After an examination is submitted, the system generates an AI-based integrity report using LangChain and Google Gemini.

The report provides a summary of the recorded examination activity and integrity analysis.

## Project Structure

```text
online-exam-monitoring-system/
│
├── app.py
├── monitoring.py
├── scoring.py
├── analytics.py
├── dashboard_data.py
├── alert_manager.py
├── ai_report_agent.py
├── ai_validation.py
├── utils.py
│
├── streamlit_dashboard.py
│
├── scripts/
│   └── generate_session_logs.py
│
├── templates/
│   ├── base.html
│   ├── register.html
│   ├── login.html
│   ├── capture_photo.html
│   ├── dashboard.html
│   ├── system_check.html
│   ├── declaration.html
│   ├── exam.html
│   ├── analytics.html
│   ├── instructions.html
│   ├── sidebar.html
│   └── submission_success.html
│
├── static/
│   ├── style.css
│   └── analytics.js
│
├── tests/
│   └── test_dashboard_data.py
│
├── data/
│
├── requirements.txt
├── .gitignore
├── LICENSE
└── README.md