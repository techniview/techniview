# TechniView Technical Specification Document

**Goal:** Create a web-based learning platform for technical computer science questions.  
**Team:** Ryan Sippy, Jason Bellerjeau, Derek Corniello.

## Version and Change Log

| Version | Date | Change | Author |
| :--- | :--- | :--- | :--- |
| 1.0 | 2026-10-30 | Initial Technical Specification Document creation | Team (Ryan Sippy, Jason Bellerjeau, Derek Corniello) |

## Architecture Summary

TechniView employs a client-server and microservices architecture utilizing a pipeline for question ingestion. The system is deployed via Docker Compose on a single Linux virtual machine to minimize costs. As depicted in the D0 High-Level System Design, the primary components include:

*   **Web UI:** The React client providing the interface for students and professors.
*   **Backend Server:** A FastAPI application that processes HTTP requests, manages authorization, and coordinates data access.
*   **Code Runner:** An isolated internal fork of Judge0 responsible for securely executing untrusted student Python code inside privileged containers.
*   **Question DB & User Data DB:** Logical data groups stored in a single MySQL 8.0 relational database to track users, submissions, and assignment configurations.

Data flows from the Web UI through JSON/REST API calls to the Backend Server. The Backend queries MySQL for application state and dispatches isolated code jobs via REST to the Code Runner. Once completed, the Code Runner sends asynchronous HTTP callbacks back to the Backend Server to finalize grades and update student progress.

## Interfaces and Data Formats

### Component Boundaries

*   **Web UI to Backend:**
    *   **Inputs:** JSON payloads (e.g., student ID, source code) and HTTP-only session cookies.
    *   **Outputs:** JSON response bodies (e.g., execution status, score, public test feedback).
    *   **Protocol:** HTTPS (REST).
    *   **Error Behavior:** Standardized API error responses returning 401 (Auth), 403 (Permissions), 404 (Not Found), 409 (Conflict), or 422 (Validation).
*   **Backend to Code Runner:**
    *   **Inputs:** JSON execution requests containing Python source code, memory limits, CPU limits, and callback URLs.
    *   **Outputs:** Asynchronous POST callback payloads to the backend containing test case results (tokens, status IDs).
    *   **Protocol:** REST via HTTP.
    *   **Error Behavior:** 429 for busy runner, 502/504 for timeouts or unavailability, mapping to an `infrastructure_error` in the database to prevent penalizing student attempts.
*   **Backend to Databases:**
    *   **Inputs:** Parameterized SQL queries using SQLAlchemy.
    *   **Outputs:** Relational rows mapped to ORM objects (e.g., Submission, User, Problem).
    *   **Protocol:** TCP.
    *   **Error Behavior:** Failed transactions initiate a rollback, surfacing a 503 error to the client without dropping the database state.

### Endpoint Table

| Endpoint | Method | Inputs (Payload/Params) | Outputs (JSON Schema) | Error Behavior |
| :--- | :--- | :--- | :--- | :--- |
| `/api/submissions` | POST | `problem_id` (int), `assignment_item_id` (int, opt), `source_code` (str) | Submission object with status, score, `public_results` | 422 on invalid input, 404 if missing, 409 on attempt limit |
| `/api/submissions/{id}` | GET | `submission_id` in path | Submission object | 404 if not found or unauthorized |
| `/api/courses/{id}/analytics/overview` | GET | `course_id` in path, optional filters (difficulty, limit, offset) | summary (Metrics), items (ProblemMetrics array) | 401/403 if unauthorized, 404 if course not found |

## Technology Stack

| Layer | Choice | Justification |
| :--- | :--- | :--- |
| **Database** | MySQL 8.0 | (REQ-02, CON-01) Supports necessary row-locking and transactions; free to host on UC VMs. |
| **Backend** | Python 3.14 (FastAPI) | (REQ-01) Aligns with team's Python knowledge; strong typing and fast JSON routing. |
| **Frontend** | React, TypeScript, Vite | (NFR-03) Team familiarity allows faster delivery of accessible UIs; static builds are inexpensive to host. |
| **Code Execution** | Judge0 (Internal Fork) | (NFR-01, NFR-02) Established tool with per-job CPU/memory isolation and privileged containers. |
| **Deployment** | Docker Compose | (CON-01) Enables deployment of multiple containers on a single affordable Linux VM. |

## Known Constraints

*   **CON-01 (Economic):** Hosting budget is $0 on UC resources and capped at $200/semester for AWS. Forces use of UC-hosted storage/compute (Docker Compose on a single VM) and rules out premium managed cloud services that exceed the cap.
*   **CON-02 (Security):** FERPA compliance. Forces encrypted, role-based UC authentication and transcript-only retention, and rules out public freeware hosting and full interview video retention to avoid AWS metering costs.
*   **CON-03 (Legal):** UC IRB approval required. Forces strict informed consent protocols enrolling only approved participants, and rules out widespread platform testing without regulatory clearance.
*   **CON-04 (Ethical):** Voluntary participation. Forces opt-in practice scenarios and rules out making the platform a mandatory coursework requirement for academic grades.

## Traceability Matrix

| Req ID | Description | Design Component (D0/D1/D2) | Status | Test Case |
| :--- | :--- | :--- | :--- | :--- |
| REQ-01 | Compile and execute Python submissions against test cases within 5 seconds. | Code Runner, SubmissionCaseResult (D1/D2) | Designed | TC-01 |
| REQ-02 | Compute and update a student's `best_score` and valid attempt counts. | StudentAssignmentProgress (D1/D2) | Designed | TC-02 |
| REQ-03 | Allow professors to create draft problems and publish canonical solutions. | Problem, ProblemTestCase (D1/D2) | Designed | TC-03 |
| REQ-04 | Assign published problem sets to course rosters with distinct dates. | Assignment, AssignmentItem (D1/D2) | Designed | TC-04 |
| REQ-05 | Enforce role-based access for test cases and metrics. | CourseMembership (D1/D2) | Designed | TC-05 |
| REQ-06 | Allow soft withdrawal of course memberships retaining history. | CourseMembership (D1/D2) | Planned | TC-06 |
| NFR-01 | Process up to 335 jobs/minute without exceeding a 10-second timeout. | Code Runner (D0/D2) | Planned | TC-07 |
| NFR-02 | Isolate code execution in privileged containers (128MB RAM, 2.0s CPU). | Code Runner (D0/D2) | In progress | TC-08 |
| NFR-03 | Web UI complies with WCAG 2.1 AA accessibility. | Web UI (D0/D2) | Planned | TC-09 |
| NFR-04 | Maintain 99.9% uptime for backend API and databases. | Backend Server, Databases (D0) | Planned | TC-10 |
| CON-01 | Economic constraints ($0 UC, $200 AWS limit). | Deployment Stack (D0/D2) | Designed | TC-11 |
| CON-02 | Security constraints (FERPA encryption & role access). | Authentication/UserSession (D1/D2) | Designed | TC-11 |
| CON-03 | Legal constraints (UC IRB approval and consent). | Web UI/Consent Forms (D0/D2) | Planned | TC-12 |
| CON-04 | Ethical constraints (Voluntary non-coercive practice). | CourseMembership (D1/D2) | Planned | TC-13 |

## Record of Advisor Review

*   **Date:** Week 8 (October 2026)
*   **Participants:** Professor William Hawkins III (Faculty Advisor), Peer Reviewers, Team (Ryan, Jason, Derek)
*   **Discussion Points:**
    *   Problem Set
    *   Front-end
    *   App Cleanup
    *   Study Design
*   **Changes Produced:**
    *   New tasks discovered for getting study design approved
    *   Consent Form
    *   Promotion Materials
    *   Script for the study
    *   How we will evaluate the study
    *   Feedback form
    *   Use Qualtrics
    *   Ideas generated for how to group problem set
    *   Feedback on what a professor would like in the front end view