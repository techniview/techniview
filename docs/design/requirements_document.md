# TechniView Requirements Document

**Goal:** Create a web-based learning platform for technical computer science questions.  
**Team:** Ryan Sippy, Jason Bellerjeau, Derek Corniello.

## Version and Change Log

| Version | Date | Change | Author |
| :--- | :--- | :--- | :--- |
| 1.0 | 2026-10-30 | Initial Requirements Document creation | Team (Ryan, Jason, Derek) |

## Purpose and Scope

The purpose of TechniView is to provide a web-based learning platform for technical computer science questions, enabling students to access, run, and track progress on practice coding problems while allowing professors to actively curate, assign, and monitor assessments without needing local development environments.

## Stakeholders and User Goals

*   **Primary Stakeholders:** Students, Professors
*   **Secondary Stakeholders:** Problem Management Team, IT Support Team
*   **Hidden Stakeholders:** Students with Disabilities, Government Education Departments and Regulators, University Administrators

**User Goals:**

*   Access and run practice coding problems in a web-based environment to improve skills without local setups (US-01).
*   Track progress and performance on coding problems to monitor growth (US-02).
*   Assign and manage coding problems to assess student understanding (US-03).
*   Create and curate high-quality coding problems for the platform (US-04).
*   Ensure the platform complies with data privacy and security regulations to protect student information (US-05).

## Glossary

*   **Student:** A user enrolled in a course who uses the platform to practice coding problems and complete assignments.
*   **Professor:** A user managing a course, curating coding problems, and assessing students through assignments.
*   **Problem Management Team:** Stakeholders responsible for creating and curating the platform's coding problems.
*   **IT Support Team:** Stakeholders ensuring the platform's availability and resolving infrastructure issues.
*   **Code Runner:** The isolated service (internal Judge0 fork) used to safely execute untrusted student Python code.
*   **Backend Server:** The FastAPI application handling data routing between the web UI and databases.
*   **Web UI:** The React-based frontend providing the interface for students and teachers.
*   **Question DB:** The database group storing problem prompts, test cases, tags, and solution metadata.
*   **User Data DB:** The database group storing user profiles, course memberships, submissions, and progress metrics.
*   **Canonical Solution:** The validated, correct solution to a problem used as a baseline to verify test cases.
*   **Test Case:** Specific input and expected output combinations used to grade student code submissions.

## Functional Requirements

| ID | Statement | MoSCoW | Source Story | Verification Method |
| :--- | :--- | :--- | :--- | :--- |
| REQ-01 | The system shall compile and execute a student's Python code submission against provided test cases and return feedback status within 5 seconds. | Must | US-01 | Test automation (Code Execution) |
| REQ-02 | The system shall compute and update a student's `best_score` and valid attempt counts in the database upon finalization of a submission. | Must | US-02 | Unit testing / DB Inspection |
| REQ-03 | The system shall allow professors to create draft coding problems, input canonical solutions, and publish them to the catalog. | Must | US-03 | End-to-End UI Testing |
| REQ-04 | The system shall permit a professor to assign published problem sets to course rosters with distinct start and due dates. | Must | US-03 | End-to-End UI Testing |
| REQ-05 | The system shall enforce role-based access, ensuring students cannot view hidden test cases, canonical solutions, or other students' metrics. | Must | US-05 | Security / Access Control Testing |
| REQ-06 | The system shall allow staff to withdraw a student course membership, retaining historical analytics data rather than deleting it. | Should | US-03 | DB Inspection / Regression Testing |

## Non-Functional Requirements

| ID | Statement | MoSCoW | Source Story | Verification Method |
| :--- | :--- | :--- | :--- | :--- |
| NFR-01 | The system shall process code execution requests at a peak concurrency of 335 jobs per minute without exceeding a 10-second timeout. | Must | US-01 | Load Testing |
| NFR-02 | The system shall isolate code execution in privileged containers with a strict memory limit of 128,000 KB and a CPU limit of 2.0 seconds per test case. | Must | US-05 | Penetration / Sandbox Escape Testing |
| NFR-03 | The frontend Web UI shall comply with WCAG 2.1 AA accessibility standards across all core student and professor workflows. | Should | US-05 | Accessibility Audit |
| NFR-04 | The backend API and databases shall maintain a 99.9% uptime during the final two weeks of the semester to ensure assignment availability. | Must | US-01 | Uptime Monitoring / Logs |

## MoSCoW Summary

**Must Have (This Release):**
*   Web-based Python code execution and per-case compilation.
*   Student progress tracking and performance dashboards.
*   Professor authoring, publishing, and assignment management.
*   Role-based data privacy and isolated containerized code execution.

**Should Have (This Release):**
*   Accessibility compliance for UI interfaces.
*   Soft-withdrawal functionality for student course rosters maintaining data history.

**Could Have (This Release):**
*   Support for additional programming languages beyond Python.
*   Advanced automated hints or intelligent code suggestions.

**Won't Have (This Release):**
*   Automated notifications (email/push) for assignment deadlines, grades, or system events.
*   Real-time collaborative coding environments or pair programming features.
*   Video or screen-recording capabilities for interview proctoring.

## Inherited Constraints

*   **CON-01 (Economic):** Hosting budget is $0 on UC resources and capped at $200/semester for AWS, restricting infrastructure to UC-hosted storage/compute.
*   **CON-02 (Security):** FERPA compliance mandates encrypted authentication and role-based access, prioritizing transcript-only retention over full video recordings.
*   **CON-03 (Legal):** UC IRB approval requires informed consent and FERPA-compliant anonymization, limiting enrollment strictly to consenting UC CS/SWE students.
*   **CON-04 (Ethical):** Participation must remain strictly voluntary and non-coercive (opt-in practice) per UC IRB expectations, disallowing required coursework use.

## Assumptions and Open Questions

*   **OQ-01:** Are assignment recipients a permanent snapshot, or should later students and reactivated members be added? (Owner: Derek Corniello, Date: 2026-10-30)
*   **OQ-02:** Should withdrawn students remain in assignment analytics and historical recipient lists? (Owner: Jason Bellerjeau, Date: 2026-10-30)
*   **OQ-03:** What notification events, channels, preferences, and delivery guarantees are required? (Owner: Ryan Sippy, Date: 2026-10-30)
*   **OQ-04:** Which privacy rules, legal jurisdiction, retention periods, and account deletion behavior apply? (Owner: Team, Date: 2026-10-30)
*   **OQ-05:** What are the production TLS, secure-cookie, CORS, secret rotation, backup, and restore targets? (Owner: Derek Corniello, Date: 2026-10-30)
*   **OQ-06:** What latency and volume targets should govern analytics and Judge0 capacity? (Owner: Team, Date: 2026-10-30)
*   **OQ-07:** Should the API normalize FastAPI HTTPException and database failures into the ApiError contract? (Owner: Derek Corniello, Date: 2026-10-30)
*   **OQ-08:** Is Python-only execution the intended product requirement or an implementation limitation? (Owner: Team, Date: 2026-10-30)