# TechniView Technical Specification Document

**Goal:** Create a web-based learning platform for technical computer science questions.  
**Team:** Ryan Sippy, Jason Bellerjeau, Derek Corniello.

## Version and Change Log

| Version | Date | Change | Author |
| :--- | :--- | :--- | :--- |
| 1.0 | 2026-10-30 | Initial Technical Specification Document creation | Team (Ryan Sippy, Jason Bellerjeau, Derek Corniello) |

## Architecture Summary

TechniView uses two Docker Compose projects on separate Linux VMs. The application VM runs the web frontend, FastAPI, application workers, and MySQL. The dedicated runner VM executes untrusted code through standalone go-judge. The [deployment guide](../deployment.md) defines the current topology; D0 is a historical design snapshot. The components are:

*   **Web UI:** The React client providing the interface for students and professors.
*   **Backend Server:** A FastAPI application that processes HTTP requests, manages authorization, and coordinates data access.
*   **Code runner:** Standalone go-judge 1.13.3 executes Python 3.14 cases in isolated jobs. Its container runs on a dedicated runner VM and needs privileged access for cgroup v2 enforcement.
*   **Database:** One MySQL 8.0 service stores problems, accounts, submissions, and assignments. "Question DB" and "User Data DB" name logical data groups, not separate services.

The browser calls the backend over HTTPS. `POST /api/submissions` reserves a submission in MySQL and returns HTTP 202 with an ID. Application workers claim queued cases, call the runner's private HTTP `/run` endpoint, store the response, and finalize grading and progress in MySQL. The browser polls the authorized submission endpoint for results. Worker recovery records an uncertain runner outcome as an infrastructure error; it does not silently rerun the case.

## Interfaces and Data Formats

### Component Boundaries

*   **Web UI to backend:** JSON requests use an HTTP-only session cookie; submission POSTs also require an `Idempotency-Key` header. Caddy terminates public HTTPS. The API returns JSON status, scores, and permitted case feedback. Authentication, authorization, missing-resource, conflict, and validation errors use 401, 403/404, 409, and 422 as appropriate.
*   **Application worker to runner:** The worker sends source, input, CPU and memory limits in an HTTP request to go-judge on the runner VM's private port 5050. The runner returns one execution report in the HTTP response. There is no callback URL or runner-owned submission database. The runner port must accept traffic only from the application VM. Ambiguous transport failures become infrastructure errors in MySQL and do not count as valid attempts.
*   **Backend and workers to MySQL:** SQLAlchemy uses private TCP connections and transactions. MySQL stores relational application state; it has no published host port in production. A failed write is rolled back. The API does not guarantee that every database failure maps to HTTP 503.

### Endpoint Table

| Endpoint | Method | Inputs (Payload/Params) | Outputs (JSON Schema) | Error Behavior |
| :--- | :--- | :--- | :--- | :--- |
| `/api/submissions` | POST | `problem_id`, optional `assignment_item_id`, `source_code`, required `Idempotency-Key` header | HTTP 202 and a queued submission with its ID; grading completes later | 422 on invalid input, 404 for an unavailable problem, 409 for active or exhausted attempts |
| `/api/submissions/{id}` | GET | Submission ID in path and session cookie | Owner-visible status, score, and permitted case feedback | 404 if missing or not owned by caller |
| `/api/courses/{id}/analytics/overview` | GET | Course ID; optional `assignment_id`, `difficulty`, `tag`, `limit`, `offset` | Summary, problem items, and pagination fields | Staff membership required; unauthorized or missing courses return 403/404 |

## Technology Stack

| Layer | Choice | Justification |
| :--- | :--- | :--- |
| **Database** | MySQL 8.0 | (REQ-02, CON-01) Supports necessary row-locking and transactions; free to host on UC VMs. |
| **Backend** | Python 3.14 (FastAPI) | (REQ-01) Aligns with team's Python knowledge; strong typing and fast JSON routing. |
| **Frontend** | React, TypeScript, Vite | (NFR-03) Team familiarity allows faster delivery of accessible UIs; static builds are inexpensive to host. |
| **Code execution** | go-judge 1.13.3 with Python 3.14 | (NFR-02) Enforces per-case CPU and memory limits inside isolated jobs on a dedicated runner VM. |
| **Deployment** | Two Docker Compose projects | (CON-01) Keeps untrusted execution separate from the application and its student data. |

## Known Constraints

*   **CON-01 (Economic):** The project budgets $0 for UC resources and at most $200 per semester for AWS. The documented deployment uses separate UC application and runner VMs; the budget needs confirmation against the allocated machines.
*   **CON-02 (Security and privacy):** Protect student accounts, submissions, and course data with HTTPS, role checks, restricted networks, and encrypted campus storage. A FERPA compliance determination, retention schedule, and account deletion policy still need institutional review.
*   **CON-03 (Research):** Obtain the applicable UC IRB determination and consent process before research enrollment. The repository does not establish that approval has been granted.
*   **CON-04 (Ethical):** Voluntary participation. Forces opt-in practice scenarios and rules out making the platform a mandatory coursework requirement for academic grades.

## Traceability Matrix

| Req ID | Description | Design Component (D0/D1/D2) | Status | Test Case |
| :--- | :--- | :--- | :--- | :--- |
| REQ-01 | Accept Python submissions asynchronously and return authorized case results when complete. | API, worker, go-judge, SubmissionCaseResult | Implemented; latency target unverified | TC-01 |
| REQ-02 | Compute and update a student's `best_score` and valid attempt counts. | StudentAssignmentProgress (D1/D2) | Designed | TC-02 |
| REQ-03 | Allow professors to create draft problems and publish canonical solutions. | Problem, ProblemTestCase (D1/D2) | Designed | TC-03 |
| REQ-04 | Assign published problem sets to course rosters with distinct dates. | Assignment, AssignmentItem (D1/D2) | Designed | TC-04 |
| REQ-05 | Enforce role-based access for test cases and metrics. | CourseMembership (D1/D2) | Designed | TC-05 |
| REQ-06 | Allow soft withdrawal of course memberships retaining history. | CourseMembership | Implemented | TC-06 |
| NFR-01 | Measure throughput and queue delay for the expected problem mix on the target VMs. | API queue, workers, go-judge | Capacity assessment pending | TC-07 |
| NFR-02 | Isolate student jobs and enforce each problem's CPU and memory limits. | go-judge on dedicated runner VM | Local integration passed; target VM check pending | TC-08 |
| NFR-03 | Web UI complies with WCAG 2.1 AA accessibility. | Web UI (D0/D2) | Planned | TC-09 |
| NFR-04 | Measure API and database availability against an approved target. | Health routes, operations monitoring | Target and baseline pending | TC-10 |
| CON-01 | UC and AWS budget limits. | Two-VM deployment | Cost validation pending | TC-11 |
| CON-02 | Student-data security and privacy. | HTTPS, sessions, role checks, backups | Institutional review pending | TC-11 |
| CON-03 | Research approval and consent. | Study process outside the application | Institutional determination pending | TC-12 |
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
