import { apiRequest } from "./client";

export type SubmissionResult = {
    case_order: number;
    status_id: number;
    friendly_message: string;
};

export type Submission = {
    id: number;
    status: string;
    done: boolean;
    score: number | null;
    is_late: boolean;
    late_approved: boolean;
    passed_count: number;
    test_count: number;
    public_results: SubmissionResult[];
    poll_url: string;
};

export function createSubmission(problemId: number, sourceCode: string) {
    return apiRequest<Submission>("/api/submissions", {
        method: "POST",
        body: JSON.stringify({
            problem_id: problemId,
            source_code: sourceCode,
        }),
    });
}

export function getSubmission(submissionId: number) {
    return apiRequest<Submission>(`/api/submissions/${submissionId}`);
}
