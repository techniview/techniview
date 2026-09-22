-- Legacy design reference. Do not apply this file.
-- Alembic migrations are the executable application schema.
-- techniview application schema draft for mysql 8.0.17 or newer
-- configure every application connection to utc
-- the backend enforces permissions and prevents edits to published content
-- it also checks total test weight and concurrent submission limits

SET NAMES utf8mb4;
SET time_zone = '+00:00';

-- identity comparisons must preserve case and trailing spaces
CREATE TABLE users (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100),
    email VARCHAR(255),
    oidc_issuer VARCHAR(255) COLLATE utf8mb4_0900_bin,
    oidc_subject VARCHAR(255) COLLATE utf8mb4_0900_bin,
    can_create_courses BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_users_identity (oidc_issuer, oidc_subject),
    KEY idx_users_email (email),
    CONSTRAINT chk_users_identity CHECK (
        (oidc_issuer IS NULL AND oidc_subject IS NULL)
        OR (oidc_issuer IS NOT NULL AND oidc_subject IS NOT NULL
            AND CHAR_LENGTH(oidc_issuer) > 0 AND CHAR_LENGTH(oidc_subject) > 0)
    ),
    CONSTRAINT chk_users_instructor CHECK (can_create_courses IN (0, 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE courses (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(150) NOT NULL,
    description TEXT,
    timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
    join_code_hash BINARY(32),
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    archived_at DATETIME(6),
    UNIQUE KEY uq_courses_join_code (join_code_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE course_memberships (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    course_id BIGINT UNSIGNED NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    role ENUM('student', 'ta', 'instructor') NOT NULL,
    joined_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    withdrawn_at DATETIME(6),
    UNIQUE KEY uq_memberships_course_user (course_id, user_id),
    UNIQUE KEY uq_memberships_id_course (id, course_id),
    KEY idx_memberships_user (user_id, withdrawn_at),
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE RESTRICT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT,
    CONSTRAINT chk_memberships_dates CHECK (
        withdrawn_at IS NULL OR withdrawn_at >= joined_at
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- copy used problems instead of editing them
-- imported problems are read only
CREATE TABLE problems (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    owner_id BIGINT UNSIGNED,
    copied_from_id BIGINT UNSIGNED,
    origin ENUM('imported', 'custom') NOT NULL DEFAULT 'custom',
    state ENUM('draft', 'published', 'archived') NOT NULL DEFAULT 'draft',
    title VARCHAR(255) NOT NULL,
    prompt MEDIUMTEXT NOT NULL,
    difficulty ENUM('easy', 'medium', 'hard') NOT NULL,
    starter_code TEXT,
    cpu_time_limit_seconds DECIMAL(6,3) NOT NULL DEFAULT 2.000,
    memory_limit_kb INT UNSIGNED NOT NULL DEFAULT 128000,
    source_dataset VARCHAR(255) COLLATE utf8mb4_0900_bin,
    source_problem_id VARCHAR(255) COLLATE utf8mb4_0900_bin,
    attribution TEXT,
    license VARCHAR(255),
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_problems_source (source_dataset, source_problem_id),
    KEY idx_problems_browse (state, difficulty),
    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE RESTRICT,
    FOREIGN KEY (copied_from_id) REFERENCES problems(id) ON DELETE RESTRICT,
    CONSTRAINT chk_problems_origin CHECK (
        (origin = 'imported' AND source_dataset IS NOT NULL
            AND source_problem_id IS NOT NULL AND attribution IS NOT NULL
            AND license IS NOT NULL)
        OR (origin = 'custom' AND owner_id IS NOT NULL
            AND source_dataset IS NULL AND source_problem_id IS NULL)
    ),
    CONSTRAINT chk_problems_cpu CHECK (
        cpu_time_limit_seconds > 0 AND cpu_time_limit_seconds <= 15
    ),
    CONSTRAINT chk_problems_memory CHECK (
        memory_limit_kb > 0 AND memory_limit_kb <= 262144
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE problem_test_cases (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    problem_id BIGINT UNSIGNED NOT NULL,
    case_order INT NOT NULL,
    visibility ENUM('public', 'hidden') NOT NULL DEFAULT 'hidden',
    input MEDIUMTEXT NOT NULL,
    expected_output MEDIUMTEXT NOT NULL,
    weight DECIMAL(10,4) NOT NULL DEFAULT 1.0000,
    UNIQUE KEY uq_cases_order (problem_id, case_order),
    UNIQUE KEY uq_cases_id_problem (id, problem_id),
    FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE RESTRICT,
    CONSTRAINT chk_cases_order CHECK (case_order > 0),
    CONSTRAINT chk_cases_weight CHECK (weight >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE question_sets (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    owner_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(150) NOT NULL,
    description TEXT,
    state ENUM('draft', 'published', 'archived') NOT NULL DEFAULT 'draft',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE question_set_items (
    question_set_id BIGINT UNSIGNED NOT NULL,
    problem_id BIGINT UNSIGNED NOT NULL,
    item_order INT NOT NULL,
    PRIMARY KEY (question_set_id, problem_id),
    UNIQUE KEY uq_set_items_order (question_set_id, item_order),
    FOREIGN KEY (question_set_id) REFERENCES question_sets(id) ON DELETE CASCADE,
    FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE RESTRICT,
    CONSTRAINT chk_set_items_order CHECK (item_order > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE assignments (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    course_id BIGINT UNSIGNED NOT NULL,
    assigned_by_membership_id BIGINT UNSIGNED NOT NULL,
    source_question_set_id BIGINT UNSIGNED,
    title VARCHAR(150) NOT NULL,
    description TEXT,
    state ENUM('draft', 'published', 'archived') NOT NULL DEFAULT 'draft',
    audience ENUM('course', 'selected') NOT NULL DEFAULT 'course',
    available_at DATETIME(6),
    due_at DATETIME(6),
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_assignments_id_course (id, course_id),
    KEY idx_assignments_course (course_id, state, due_at),
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE RESTRICT,
    FOREIGN KEY (assigned_by_membership_id, course_id)
        REFERENCES course_memberships(id, course_id) ON DELETE RESTRICT,
    FOREIGN KEY (source_question_set_id) REFERENCES question_sets(id)
        ON DELETE RESTRICT,
    CONSTRAINT chk_assignments_dates CHECK (
        due_at IS NULL OR available_at IS NULL OR due_at >= available_at
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- changing a question set cannot change these assignment items
CREATE TABLE assignment_items (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    assignment_id BIGINT UNSIGNED NOT NULL,
    problem_id BIGINT UNSIGNED NOT NULL,
    item_order INT NOT NULL,
    points DECIMAL(10,4) NOT NULL DEFAULT 1.0000,
    submission_limit INT,
    UNIQUE KEY uq_assignment_items_problem (assignment_id, problem_id),
    UNIQUE KEY uq_assignment_items_order (assignment_id, item_order),
    UNIQUE KEY uq_assignment_items_id_problem (id, problem_id),
    FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE RESTRICT,
    FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE RESTRICT,
    CONSTRAINT chk_assignment_items_order CHECK (item_order > 0),
    CONSTRAINT chk_assignment_items_points CHECK (points >= 0),
    CONSTRAINT chk_assignment_items_limit CHECK (
        submission_limit IS NULL OR submission_limit > 0
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- course_id keeps recipients in the same course as the assignment
CREATE TABLE assignment_recipients (
    assignment_id BIGINT UNSIGNED NOT NULL,
    membership_id BIGINT UNSIGNED NOT NULL,
    course_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (assignment_id, membership_id),
    FOREIGN KEY (assignment_id, course_id) REFERENCES assignments(id, course_id)
        ON DELETE CASCADE,
    FOREIGN KEY (membership_id, course_id) REFERENCES course_memberships(id, course_id)
        ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- queued and running submissions reserve an attempt
-- infrastructure errors do not count toward submission limits
CREATE TABLE submissions (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    student_id BIGINT UNSIGNED NOT NULL,
    problem_id BIGINT UNSIGNED NOT NULL,
    assignment_item_id BIGINT UNSIGNED,
    source_code MEDIUMTEXT NOT NULL,
    language_id SMALLINT UNSIGNED NOT NULL DEFAULT 71,
    status ENUM(
        'queued', 'running', 'passed', 'failed', 'compile_error',
        'runtime_error', 'timeout', 'resource_limit', 'infrastructure_error'
    ) NOT NULL DEFAULT 'queued',
    score DECIMAL(9,8),
    submitted_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    completed_at DATETIME(6),
    late_accepted_by BIGINT UNSIGNED,
    feedback TEXT,
    UNIQUE KEY uq_submissions_id_problem (id, problem_id),
    KEY idx_submissions_student_history (student_id, problem_id, submitted_at),
    KEY idx_submissions_attempts (assignment_item_id, student_id, status),
    KEY idx_submissions_pending (status, submitted_at),
    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE RESTRICT,
    FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE RESTRICT,
    FOREIGN KEY (assignment_item_id, problem_id)
        REFERENCES assignment_items(id, problem_id) ON DELETE RESTRICT,
    FOREIGN KEY (late_accepted_by) REFERENCES users(id) ON DELETE RESTRICT,
    CONSTRAINT chk_submissions_python CHECK (language_id = 71),
    CONSTRAINT chk_submissions_score CHECK (score IS NULL OR score BETWEEN 0 AND 1),
    CONSTRAINT chk_submissions_completion CHECK (
        (status IN ('queued', 'running') AND completed_at IS NULL AND score IS NULL)
        OR (status = 'infrastructure_error' AND completed_at IS NOT NULL
            AND score IS NULL)
        OR (status IN ('passed', 'failed', 'compile_error', 'runtime_error',
                      'timeout', 'resource_limit')
            AND completed_at IS NOT NULL AND score IS NOT NULL)
    ),
    CONSTRAINT chk_submissions_dates CHECK (
        completed_at IS NULL OR completed_at >= submitted_at
    ),
    CONSTRAINT chk_submissions_late_acceptance CHECK (
        late_accepted_by IS NULL
        OR (assignment_item_id IS NOT NULL AND completed_at IS NOT NULL
            AND score IS NOT NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- students receive only aggregate feedback for hidden tests
-- problem_id keeps the submission and test case on the same problem
-- a test passes when judge0_status_id is 3 and infrastructure_error is false
CREATE TABLE submission_case_results (
    submission_id BIGINT UNSIGNED NOT NULL,
    test_case_id BIGINT UNSIGNED NOT NULL,
    problem_id BIGINT UNSIGNED NOT NULL,
    judge0_token CHAR(36) CHARACTER SET ascii COLLATE ascii_bin,
    callback_token_hash BINARY(32),
    judge0_status_id SMALLINT UNSIGNED,
    infrastructure_error BOOLEAN NOT NULL DEFAULT FALSE,
    execution_time_ms DECIMAL(12,3),
    memory_kb INT UNSIGNED,
    stdout TEXT,
    stderr TEXT,
    compile_output TEXT,
    PRIMARY KEY (submission_id, test_case_id),
    UNIQUE KEY uq_case_results_token (judge0_token),
    UNIQUE KEY uq_case_results_callback_token (callback_token_hash),
    KEY idx_case_results_pending (infrastructure_error, judge0_status_id),
    FOREIGN KEY (submission_id, problem_id) REFERENCES submissions(id, problem_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (test_case_id, problem_id) REFERENCES problem_test_cases(id, problem_id)
        ON DELETE RESTRICT,
    CONSTRAINT chk_case_results_status CHECK (
        judge0_status_id IS NULL OR judge0_status_id BETWEEN 1 AND 14
    ),
    CONSTRAINT chk_case_results_infrastructure CHECK (infrastructure_error IN (0, 1)),
    CONSTRAINT chk_case_results_time CHECK (
        execution_time_ms IS NULL OR execution_time_ms >= 0
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
