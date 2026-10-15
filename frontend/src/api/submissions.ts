import { apiRequest } from "./client";

export type SubmissionResult = {
    case_order: number;
    status_id: number | null;
    friendly_message: string;
    input: string;
    expected_output: string;
    stdout: string | null;
    stderr: string | null;
    compile_output: string | null;
    execution_time_ms: number | null;
    memory_kb: number | null;
};

export type Submission = {
    id: number;
    problem_id: number;
    assignment_item_id: number | null;
    status: string;
    done: boolean;
    score: number | null;
    is_late: boolean;
    late_approved: boolean;
    passed_count: number;
    test_count: number;
    public_results: SubmissionResult[];
    primary_error: string | null;
    python_exception_type: string | null;
    submitted_at: string;
    completed_at: string | null;
    poll_url: string;
    source_code?: string;
};

export function createSubmission(
    problemId: number,
    sourceCode: string,
    assignmentItemId?: number,
) {
    return apiRequest<Submission>("/api/submissions", {
        method: "POST",
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
