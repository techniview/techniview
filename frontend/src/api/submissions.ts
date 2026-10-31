import { apiRequest } from "./client";

export type SubmissionResult = {
    case_order: number;
    status_id: number | null;
    phase: ExecutionPhase;
    friendly_message: string;
    input: string;
    expected_output: string;
    stdout: string | null;
    stderr: string | null;
    compile_output: string | null;
    execution_time_ms: number | null;
    memory_kb: number | null;
};

export type ExecutionPhase =
    | "waiting_to_send"
    | "sending_to_go_judge"
    | "waiting_on_go_judge"
    | "running_on_go_judge"
    | "complete";

export type Submission = {
    id: number;
    problem_id: number;
    assignment_item_id: number | null;
    status: string;
    failure_code: string | null;
    failure_message: string | null;
    retryable: boolean;
    phase: ExecutionPhase;
    done: boolean;
    is_practice_run: boolean;
    score: number | null;
    is_late: boolean;
    late_approved: boolean;
    passed_count: number;
    test_count: number;
    public_results: SubmissionResult[];
    primary_error: string | null;
    python_exception_type: string | null;
    submitted_at: string;
    started_at: string | null;
    completed_at: string | null;
    wait_seconds: number | null;
    execution_seconds: number | null;
    poll_url: string;
    source_code?: string;
};

export type ComplexityAnalysis = {
    status:
        "disabled" | "unavailable" | "queued" | "processing" | "complete" | "failed";
    time_complexity: string | null;
    space_complexity: string | null;
    model: string;
    prompt_version: string;
    error_code: string | null;
    analyzed_at: string | null;
};

export function createSubmission(
    problemId: number,
    sourceCode: string,
    idempotencyKey: string,
    assignmentItemId?: number,
) {
    return apiRequest<Submission>("/api/submissions", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify({
            problem_id: problemId,
            source_code: sourceCode,
            assignment_item_id: assignmentItemId,
        }),
    });
}

export function getSubmission(submissionId: number) {
    return apiRequest<Submission>(`/api/submissions/${submissionId}`);
}

export function getSubmissionComplexity(submissionId: number) {
    return apiRequest<ComplexityAnalysis>(
        `/api/submissions/${submissionId}/complexity`,
    );
}

export function listSubmissions(
    options: {
        problem_id?: number;
        assignment_item_id?: number;
        status?: string;
        limit?: number;
        offset?: number;
    } = {},
) {
    const params = new URLSearchParams();
    Object.entries(options).forEach(([key, value]) => params.set(key, String(value)));
    const query = params.toString();
    return apiRequest<{
        items: Submission[];
        total: number;
        limit: number;
        offset: number;
    }>(`/api/submissions${query ? `?${query}` : ""}`);
}
