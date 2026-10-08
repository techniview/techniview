# TechniView D1: Detailed design

## Header, scope, and conventions

**Project title:** TechniView Design Diagram  
**Goal statement:** Create a web-based learning platform for technical computer science questions.

This document details the Database component and its submission grading and assignment progress computations. It defers the Backend Server's remaining routes, the Code Runner internals, and the Web UI to D2. The design is based on repository commit `2257305`. The User Data DB and Question DB are table groups in one MySQL 8.0 database; the Backend Server calls the repository's internal Judge0 fork.

The D0 figure uses stick figures for users, cylinders for databases, squares for user interfaces, and rectangles with inner lines for servers. In the D1 data model, each box is a table containing fields that affect behavior. Dashed boxes are Question DB tables; solid boxes are User Data DB tables. Lines are foreign-key relationships, and their labels name the relationship. `PK` means primary key, `FK` means foreign key, `UQ` marks a field in a unique constraint, and `IX` marks an indexed field. A `UQ` or `IX` mark may be part of a composite key; the index table gives the exact columns. Crow's-foot marks show cardinality at both ends: a bar means one, a circle means zero, and a three-pronged foot means many.

## Data model

Figure 1 shows the 10 tables selected for grading and assignment progress from the larger ORM model. It supports US-01 (submission and feedback), US-02 (student progress), and US-03 (assignments and assessment). The compact drawing leaves out `AssignmentItem.item_order` and `StudentAssignmentProgress.retry_count`. `item_order` controls question order. The current grader gives every test case equal weight. Practice progress is stored in `StudentPracticeProgress`, which is outside this assignment-focused figure.

The relational model fits because grading relies on foreign keys, unique constraints, transactions, and row locks. The composite foreign key from `submissions` to `assignment_items` requires an assigned submission's `problem_id` to match the item's `problem_id`. Foreign keys also protect submission and test-case references; the service selects cases from the submitted problem. Row locks protect callback and progress updates. A document store would move more of these checks into application code.

### Figure 1. D1 data model

The editable source for this diagram is [Figure_1_data_model.svg](Figure_1_data_model.svg). The PNG included with this document is the figure image.

```mermaid
erDiagram
    USER ||--o{ COURSE_MEMBERSHIP : has
    COURSE ||--o{ COURSE_MEMBERSHIP : has
    USER ||--o{ SUBMISSION : makes
    PROBLEM ||--o{ SUBMISSION : receives
    ASSIGNMENT ||--o{ ASSIGNMENT_ITEM : contains
    PROBLEM ||--o{ ASSIGNMENT_ITEM : used_in
    ASSIGNMENT_ITEM o|--o{ SUBMISSION : answers
    SUBMISSION ||--o{ SUBMISSION_CASE_RESULT : has
    PROBLEM_TEST_CASE ||--o{ SUBMISSION_CASE_RESULT : graded_in
    USER ||--o{ STUDENT_ASSIGNMENT_PROGRESS : has
    ASSIGNMENT_ITEM ||--o{ STUDENT_ASSIGNMENT_PROGRESS : collects

    USER {
        int id PK
        string email UQ
        string role
        string password_hash
    }
    COURSE {
        int id PK
        string name
        string timezone
        string join_code_hash UQ
    }
    COURSE_MEMBERSHIP {
        int id PK
        int course_id FK
        int user_id FK
        string role
        datetime withdrawn_at
    }
    PROBLEM {
        int id PK
        string origin
        string state IX
        string difficulty IX
        string execution_mode
        decimal cpu_time_limit_seconds
        int memory_limit_kb
        string canonical_solution
    }
    PROBLEM_TEST_CASE {
        int id PK
        int problem_id FK
        int case_order UQ
        string visibility
        string input
        string expected_output
    }
    ASSIGNMENT {
        int id PK
        int course_id FK
        string state IX
        datetime due_at
    }
    ASSIGNMENT_ITEM {
        int id PK
        int assignment_id FK
        int problem_id FK
        int item_order
        decimal points
        int submission_limit
    }
    SUBMISSION {
        int id PK
        int student_id FK
        int problem_id FK
        int assignment_item_id FK
        string status IX
        decimal score
        boolean is_late
        datetime submitted_at
    }
    SUBMISSION_CASE_RESULT {
        int submission_id PK, FK
        int test_case_id PK, FK
        string judge0_token UQ
        string callback_token_hash UQ
        int judge0_status_id
        boolean infrastructure_error
        decimal execution_time_ms
    }
    STUDENT_ASSIGNMENT_PROGRESS {
        int student_id PK, FK
        int assignment_item_id PK, FK
        decimal best_score
        datetime first_opened_at
        datetime first_passed_at
        int valid_attempt_count
        int retry_count
        int wrong_answer_count
        int compile_error_count
        int runtime_error_count
        int timeout_count
        int resource_limit_count
    }
```

| Structural decision | Choice | Reason and requirement |
|---|---|---|
| Course roles | `CourseMembership` entity, not a role attribute on `User` | A person can have different roles in different courses. `withdrawn_at` keeps membership history. US-03. |
| Problems in an assignment | `AssignmentItem` entity, not a bare link | It holds points, order, and submission limit. US-03. |
| Per-test results | `SubmissionCaseResult` entity, not a JSON column | Judge0 reports cases separately; each row stores its own token and verdict. US-01, AC-01.1. |
| Progress | `StudentAssignmentProgress` row, updated on finalization | Dashboard reads one row per student and assignment item. US-02, US-03. |
| Submission to assignment item | A submission references zero or one assignment item; an item can have many submissions | A submission answers at most one assigned problem. Practice submissions leave the reference null. US-01, US-03. |
| Difficulty and visibility | Enum attributes, not entities | These are fixed values with no independent data or relationships. US-01. |
| Storage model | Relational MySQL 8.0 | Foreign keys, unique constraints, transactions, and row locks enforce grading integrity. US-01, US-02. |

| Indexed or unique columns | Why |
|---|---|
| `users(email)` unique | Login lookup and duplicate account prevention. |
| `course_memberships(course_id, user_id)` unique; `course_id` and `user_id` indexed | Enforce one membership per user and course; support course rosters and reverse lookup by user. |
| `problem_test_cases(problem_id, case_order)` unique | Load a problem's cases in stable order and prevent duplicate case positions. |
| `assignments(course_id)` and `assignments(state)` | Filter assignments by course and state. |
| `problems(state)` and `problems(difficulty)` | Filter the problem bank by publication state and difficulty. |
| `submissions(student_id, problem_id)` | Filter a student's submissions by problem. |
| `submissions(status)` | Filter submissions by queued, running, or terminal state. |
| `assignment_items(assignment_id, problem_id)` unique | Prevent duplicate problems in one assignment. |
| `assignment_items(assignment_id, item_order)` unique | Prevent duplicate positions in an assignment. |
| `assignment_items(id, problem_id)` unique | Support the composite foreign key from a submission to its assignment item. |
| `submissions(id, problem_id)` unique | Provide a unique submission/problem pair for related records. |
| `assignment_items(id, problem_id)` unique | Support the assignment-item/problem pair checked when a submission is created. |
| `submissions(id, problem_id)` unique | Provide a unique submission/problem pair for related records. |
| `student_practice_progress(student_id, problem_id)` primary key | Find or lock one student's practice progress row. |
| `submission_case_results(judge0_token)` unique | Match a Judge0 report to its case row. |
| `submission_case_results(callback_token_hash)` unique | Find and authenticate callbacks without storing the callback secret. |
| `submissions(id, problem_id)` unique | Provide a unique submission/problem pair for related records. |
| `student_practice_progress(student_id, problem_id)` primary key | Find or lock one student's practice progress row. |
| `student_practice_progress(student_id, problem_id)` primary key | Find or lock one student's practice progress row. |
| `student_assignment_progress(student_id, assignment_item_id)` primary key | Find or lock one student's progress row. |
| `user_sessions(expires_at)` | Find expired sessions for cleanup. |

## Core algorithms

Planning size: 500 problems with 8,371 test cases, about 16.7 cases per problem on average, median 10, maximum 122, 50 students and 30 assignment items per course, and a peak of about 20 submissions per minute. These are estimates, not measured load. US-01 and AC-01.1 drive grading. US-02 and US-03 drive progress reporting.

### Algorithm 1: Submission grading

**Purpose.** Run a student's Python code against every test case in Judge0 and turn the reports into one status and score. A wrong verdict produces a wrong grade (US-01, AC-01.1).

**Inputs and outputs.** `problem_id: int` must be greater than zero. `assignment_item_id: int | None` is optional and, when present, must be greater than zero. `source_code: str` must contain 1 to 65,535 UTF-8 bytes. `wait: bool` is an optional query parameter that defaults to false. The server loads the problem's test cases, CPU limit (`Decimal` seconds, default 2.0), and memory limit (`int` KB, default 128,000). It creates a `Submission` with an enum status, nullable decimal `score` from 0 to 1, nullable `primary_error`, and one `SubmissionCaseResult` per test case.

**Steps.** The server checks problem visibility. For an assignment item, it verifies that the item is published, available, and assigned to the caller. It enforces the attempt limit, creates or locks the progress row, records whether the submission is late, and inserts the queued submission. It creates one result row per test case with a random callback token stored as a SHA-256 hash. It then sends one HTTP request per case to Judge0, in sequence. Each job runs asynchronously on Judge0 workers. Call-based problems use a wrapper that calls the student's function and prints JSON. A callback locks and updates its case row. When all cases finish, the server sets status and score. Each case has equal weight. The score is `passed_case_count / total_case_count`. Failure priority is compilation error, timeout, resource limit, runtime error, then wrong answer.

**Complexity and scale.** With `T` test cases, the server makes `T` sequential Judge0 submission calls and creates or updates `O(T)` result rows. Total work is `O(T)` plus code execution. At the planning peak, the catalog average means about 335 Judge0 jobs per minute; a 122-case problem can produce 2,440 jobs per minute if every submission uses that problem. Submission latency includes the sum of the sequential HTTP request times; execution and callback time depend on Judge0's queue. At 100 times the estimated submission rate, the average becomes about 33,500 jobs per minute. That growth matters, but capacity has not been measured. Measure request latency and queue depth before choosing concurrent submissions, batch requests, or more workers.

**Why this approach.** Judge0 handles the security-sensitive sandbox, which the team has no experience building. A separate job per case gives each case its own limits and verdict. Callbacks deliver results after the browser closes. `GET /api/submissions/{id}` is the polling fallback.

**Edge cases.** Empty source is rejected with 422. A problem with no test cases returns 409. Duplicate callbacks and callbacks received after finalization cannot change the final grade. Failure ties use the fixed priority above. Judge0 failures return 429, 502, or 504; infrastructure failures do not count against the student's attempt limit.

### Algorithm 2: Progress aggregation

**Purpose.** For an assignment submission, update the student's `StudentAssignmentProgress` row, then summarize assignment progress for professors (D0 interface I6, US-02, and US-03). Practice submissions update `StudentPracticeProgress` through the same finalization path. Professor course analytics read assignment progress only.

**Inputs and outputs.** The update input is a finalized `Submission` and its locked `StudentAssignmentProgress` row, or `StudentPracticeProgress` row when `assignment_item_id` is null. The row stores `best_score: Decimal`, `first_opened_at: datetime | None`, `first_passed_at: datetime | None`, `valid_attempt_count: int`, `retry_count: int`, and five integer error counters. The analytics read accepts `course_id: int`, optional `assignment_id: int`, optional `difficulty: easy | medium | hard`, optional `tag: str`, `limit: int` from 1 to 100 (default 50), and `offset: int` >= 0 (default 0).

The response's `summary` and each item's `metrics` have integer `assigned_count`, `started_count`, `completed_count`, `total_valid_attempts`, and `total_retries`; `completion_rate: float | None` as a ratio from 0 to 1; `avg_completion_seconds` and `median_completion_seconds` as seconds or null; `avg_retries_per_student: float | None`; and `errors` with integer `wrong_answer`, `compile_error`, `runtime_error`, `timeout`, and `resource_limit` counters. Each item is `{problem: ProblemSummary, metrics: Metrics}`. The outer response also has `items`, `total`, `limit`, and `offset`.

**Steps.** Finalization skips infrastructure errors, increments the valid attempt and matching error counter, and updates `retry_count`. The code updates `best_score` only for on-time or approved-late work and sets `first_passed_at` on the first eligible passing submission. On analytics reads, the server joins assignment items to recipients and membership rows, left-joins progress, and includes non-draft assignments. It filters difficulty and tag, groups metrics by problem in Python, sorts by title and ID, then slices the result for `limit` and `offset`.

**Complexity and scale.** The update is `O(1)` after the matching progress row is found. A course overview reads `R = assignment items × recipients` records, then groups them and sorts the problem summaries: `O(R + P log P)`, where `P` is the number of distinct problems. At the planning size, `R` is about 1,500. At 100 times that size, it is about 150,000. The larger read may take seconds with grouping in Python; that is a projection, not a measurement. Pagination slices after loading and sorting all records. The ORM model has analytics rollup tables if profiling shows this query is too slow.

**Why this approach.** Write-time counters avoid recounting every submission for each dashboard read. `best_score` means a retry cannot lower a student's recorded best result.

**Edge cases.** With no assigned rows, counts are zero and rates and completion times are null. Repeated callbacks do not double-count a finalized submission. Equal best scores leave the existing value unchanged. Draft assignments are excluded; archived assignments are included. Withdrawn students are currently included in course analytics because the query does not filter them. Confirm that roster rule before D2. A late pass does not count toward `best_score` or completion time unless it is approved.

## Build-versus-reuse decisions

| Piece | Build or reuse | Library or service | License | Maturity, performance, and fit | Reason |
|---|---|---|---|---|---|
| Code sandbox | Reuse | Internal Judge0 fork, upstream 1.13.1 | GPL-3.0 | Established judge; worker execution enforces CPU and memory limits; requires privileged containers. | The team knows REST integration, not sandbox security. Keep it separate and review obligations before redistribution. |
| Database | Reuse | MySQL 8.0 | GPL-2.0 | Mature server with transactions, row locks, and composite keys; fits the estimated course load. | The project uses it for application data, separately from Judge0's PostgreSQL. |
| ORM and migrations | Reuse | SQLAlchemy 2, Alembic, PyMySQL | MIT | Established Python tools; synchronous transactions and indexed queries fit the current load. | The codebase uses typed SQLAlchemy models and Alembic revisions. |
| API framework | Reuse | FastAPI, Uvicorn, Pydantic | MIT, BSD-3-Clause | Established Python stack; validation and generated API docs fit the contract. | Reuse for request validation and JSON API documentation. |
| Password hashing and dates | Reuse | Python `hashlib.scrypt`, `datetime`, `secrets` | PSF | Standard library; avoids extra dependencies for password hashing, tokens, and UTC dates. | Do not hand-roll cryptography or date parsing. |
| Sessions | Build | `UserSession` model and standard library token functions | MIT for this repository | Small server-side implementation; hashed, expiring, revocable session tokens fit one API. | The code stores only a hash of the random cookie token. |
| Grading and progress rules | Build | TechniView code | MIT | Small data volume; rules are specific to TechniView's assignment and scoring behavior. | These rules define the product behavior in the algorithms. |
| Problem bank | Reuse | `backend/data/problem_catalog.json` | MIT | 500 audited problems; import validates required fields and source version. | Preserve the APPS and APPS+ attribution recorded in the catalog. |

## API contract

The detailed endpoints use JSON under `/api` and the `techniview_session` cookie. Successful requests return HTTP 200. `POST /api/submissions` accepts an optional `wait` query parameter, default false. Query pagination uses `limit` default 50 and range 1 to 100, and `offset` default 0 and range 0 or greater.

| Endpoint | Inputs | Output |
|---|---|---|
| `POST /api/submissions` | JSON body: `problem_id: int`, required, > 0; `assignment_item_id: int | null`, optional, if present > 0; `source_code: str`, required, 1 to 65,535 UTF-8 bytes. Extra fields are rejected. Optional query `wait: bool`, default false. | HTTP 200 and a `Submission` response. With `wait=false`, normally queued or running; `wait=true` waits for each Judge0 job before responding. |
| `GET /api/submissions/{submission_id}` | Path `submission_id: int`, required. IDs for existing submissions are positive; missing, non-owned, or other values return 404. Session cookie required. | HTTP 200 and the current `Submission` response, visible only to its owner. |
| `GET /api/courses/{course_id}/analytics/overview` | Path `course_id: int`, required, integer. Optional query `assignment_id: int`; `difficulty: easy | medium | hard`; `tag: str`; `limit: int` 1–100, default 50; `offset: int` >=0, default 0. Staff membership required. | HTTP 200 and `{summary: Metrics, items: ProblemMetrics[], total: int, limit: int, offset: int}`. |

`Submission` is `{id: int, status: SubmissionStatus, done: bool, score: Decimal | null, is_late: bool, late_approved: bool, passed_count: int, test_count: int, public_results: PublicResult[], poll_url: str}`. `SubmissionStatus` is `queued | running | passed | failed | compile_error | runtime_error | timeout | resource_limit | infrastructure_error`. `PublicResult` is `{case_order: int, status_id: int | null, friendly_message: str}`; status IDs are Judge0 values 1 through 14. `passed_count` and `test_count` include hidden tests, but `public_results` contains public cases only.

`Metrics` is `{assigned_count: int, started_count: int, completed_count: int, completion_rate: float | null, avg_completion_seconds: float | null, median_completion_seconds: float | null, total_valid_attempts: int, total_retries: int, avg_retries_per_student: float | null, errors: ErrorCounts}`. `ErrorCounts` is `{wrong_answer: int, compile_error: int, runtime_error: int, timeout: int, resource_limit: int}`. `ProblemMetrics` is `{problem: ProblemSummary, metrics: Metrics}`. `ProblemSummary` is `{id: int, title: string, difficulty: easy|medium|hard, origin: imported|custom, state: draft|published|archived, tags: string[], typed_tags: ProblemTag[], source_category: string | null}`. `ProblemTag` is `{name: string, slug: string, kind: general|technique|problem_type}`. Completion times use seconds; rates are ratios from 0 to 1.

| HTTP status | Code or body | When it happens |
|---|---|---|
| 401 | `authentication_required` or `invalid_session` | Missing or expired session cookie. |
| 403 | `staff_required` | A student or non-staff member calls analytics. |
| 404 | `course_not_found`, `problem_not_found`, `assignment_item_not_found`, or `submission_not_found` | Resource is missing, unavailable to caller, or not owned by caller. |
| 409 | `problem_has_no_tests` or `submission_limit_reached` | Problem has no cases or the assignment attempt limit is reached. |
| 422 | `validation_error` | Missing field, invalid type or range, extra field, or source exceeds the byte limit. |
| 429 | `{"detail":"runner busy, try again"}` | Judge0 rejects a request because it is busy. |
| 502 | `{"detail":"runner unavailable"}` | Judge0 is unavailable or returns an invalid response. |
| 504 | `{"detail":"runner timed out"}` | Judge0 does not respond before the request timeout. |

`ApiError` and request-validation failures use `{error: {code: string, message: string, details: object}}`; validation details include field diagnostics. Runner errors use FastAPI's `{detail: string}` body. A runner failure marks the reserved submission `infrastructure_error`, which does not count toward the assignment attempt limit.

Example request:

```http
POST /api/submissions
Content-Type: application/json
Cookie: techniview_session=<session>

{"problem_id":1,"assignment_item_id":null,"source_code":"def sum_list(values):\\n    return sum(values)"}
```

Example response:

```json
{
  "id": 42,
  "status": "queued",
  "done": false,
  "score": null,
  "is_late": false,
  "late_approved": false,
  "passed_count": 0,
  "test_count": 2,
  "public_results": [
    {"case_order": 1, "status_id": 1, "friendly_message": "In queue. Waiting for a worker."}
  ],
  "poll_url": "/api/submissions/42"
}
```

Versioning: routes will move under `/api/v1` before external clients depend on them, while database changes use Alembic revisions. Removing or renaming a response field, changing a field's type or unit, or making an optional input required is a breaking API change.

## Technology choices with justification

**Database: MySQL 8.0.** Team skill fit: the team used MySQL in its databases course. License: GPL-2.0 for the server distribution. Community support: MySQL has a large user and operator base. Performance: transactions, row locks, composite keys, and indexed lookups fit the expected course workload. Cost and hosting: the server is free to run in a container on one project VM. We chose it over PostgreSQL for application data because the Judge0 stack already runs its own PostgreSQL service, which keeps application data separate from Judge0 state.

**Backend: Python 3.14 with FastAPI.** Team skill fit: Python is the team's shared language and the language students submit. License: Python uses the PSF license; FastAPI and Pydantic use MIT; Uvicorn uses BSD-3-Clause. Community support: both have active ecosystems, and FastAPI builds API documentation from schemas. Performance: request processing is small compared with code execution in Judge0. Cost and hosting: the software is free and runs in the existing backend container. We chose this over Node.js with Express so the API and grading wrappers use one language.

**Front end: React, TypeScript, and Vite.** Team skill fit: team members have used React in prior projects. License: React and Vite use MIT; TypeScript uses Apache-2.0. Community support: all three have broad adoption and documentation. Performance: Vite builds static assets; expected course pages do not need server-side rendering. Cost and hosting: the assets can be served from the same VM. The current Compose setup runs Vite's development server; production should serve the built assets. We chose this over a server-rendered Python front end because the team has more React experience.

**Code execution and messaging: internal Judge0 fork with HTTP callbacks.** Team skill fit: the team knows how to call REST services, but has no experience building a secure sandbox. License: the fork is GPL-3.0; it is isolated as a service, and redistribution obligations must be reviewed before distribution. Community support: the fork is based on the established Judge0 1.13.1 release. Performance: worker execution applies per-case CPU and memory limits, but peak capacity needs measurement. Cost and hosting: the software is free, though workers require privileged containers and may need a separate VM as load grows. The app sends one request per case and receives callbacks; Redis and PostgreSQL are internal Judge0 dependencies, not a TechniView job queue.

**Hosting: Docker Compose on one Linux VM.** Team skill fit: the team uses Compose to start the same services locally and on the server. License: Docker Compose is Apache-2.0; the VM's Linux distribution has its own license. Community support: Compose is common for small multi-service deployments. Performance: one VM fits one or two courses under the planning estimates; move Judge0 workers to another VM if measurements show contention. Cost and hosting: a university or student-credit VM keeps cost low. We chose this over Kubernetes because this project does not need a cluster or its additional operating work.
