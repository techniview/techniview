export type ErrorCounts = {
    wrong_answer: number;
    compile_error: number;
    runtime_error: number;
    timeout: number;
    resource_limit: number;
};

export type AnalyticsMetrics = {
    assigned_count: number;
    started_count: number;
    completed_count: number;
    completion_rate: number | null;
    avg_completion_seconds: number | null;
    median_completion_seconds: number | null;
    total_valid_attempts: number;
    total_retries: number;
    avg_retries_per_student: number | null;
    errors: ErrorCounts;
};

export type AnalyticsFilters = {
    difficulty: "easy" | "medium" | "hard" | null;
    tag: string | null;
};

export type StudentAnalytics = {
    metrics: AnalyticsMetrics;
    filters: AnalyticsFilters;
};

export type ProblemSummary = {
    id: number;
    title: string;
    difficulty: "easy" | "medium" | "hard";
    origin: "imported" | "custom";
    state: "draft" | "published" | "archived";
    tags: string[];
};

export type ProblemAnalytics = {
    problem: ProblemSummary;
    metrics: AnalyticsMetrics;
};

export type StudentProblemAnalytics = {
    student: {
        id: number;
        name: string;
        email: string;
        role: "student" | "professor";
    };
    problem: ProblemSummary;
    metrics: AnalyticsMetrics;
};

export type ClassAnalytics = {
    summary: AnalyticsMetrics;
    items: ProblemAnalytics[];
    total: number;
    limit: number;
    offset: number;
};
