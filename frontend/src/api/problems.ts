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
};

export function getProblem(problemId: number) {
    return apiRequest<ProblemDetail>(`/api/problems/${problemId}`);
}

export function startProblem(problemId: number) {
    return apiRequest<undefined>(`/api/problems/${problemId}/start`, {
        method: "POST",
    });
}

export function getAvailableProblems() {
    return apiRequest<ProblemListResponse>("/api/problems?limit=100");
}
