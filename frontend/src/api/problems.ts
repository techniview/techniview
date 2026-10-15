import { apiRequest } from "./client";

export type ProblemSummary = {
    id: number;
    title: string;
    difficulty: "easy" | "medium" | "hard";
    origin: "imported" | "custom";
    state: "draft" | "published" | "archived";
    tags: string[];
    typed_tags: Array<{
        name: string;
        slug: string;
        kind: "general" | "technique" | "problem_type";
    }>;
    source_category: string | null;
    available_assignment_item_id: number | null;
};

export type ProblemListResponse = {
    items: ProblemSummary[];
    total: number;
    limit: number;
    offset: number;
};

export type ProblemDetail = {
    id: number;
    title: string;
    difficulty: "easy" | "medium" | "hard";
    origin: "imported" | "custom";
    state: "draft" | "published" | "archived";
    tags: string[];
    prompt: string;
    execution_mode: "call_based" | "stdin_stdout";
    function_name: string;
    starter_code: string;
    public_tests: Array<{
        id: number;
        case_order: number;
        input: string;
        expected_output: string;
    }>;
    test_count: number;
    attribution: string | null;
    license: string | null;
    assignment_contexts: Array<{
        assignment_item_id: number;
        assignment_title: string;
        course_id: number;
        course_name: string;
    }>;
};

export function getProblem(problemId: number) {
    return apiRequest<ProblemDetail>(`/api/problems/${problemId}`);
}

export function startProblem(problemId: number, assignmentItemId?: number) {
    const query =
        assignmentItemId === undefined ? "" : `?assignment_item_id=${assignmentItemId}`;
    return apiRequest<undefined>(`/api/problems/${problemId}/start${query}`, {
        method: "POST",
    });
}

export type PublicRunResult = {
    passed_count: number;
    test_count: number;
    public_results: Array<{
        case_order: number;
        status_id: number;
        input: string;
        expected_output: string;
        stdout: string | null;
        stderr: string | null;
        compile_output: string | null;
    }>;
};

export function runPublicCases(problemId: number, sourceCode: string) {
    return apiRequest<PublicRunResult>(`/api/problems/${problemId}/run`, {
        method: "POST",
        body: JSON.stringify({ source_code: sourceCode }),
    });
}

export function getAvailableProblems(offset = 0) {
    return apiRequest<ProblemListResponse>(`/api/problems?limit=100&offset=${offset}`);
}
