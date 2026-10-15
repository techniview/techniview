import { apiRequest } from "./client";
import type { ProblemSummary } from "./problems";

export type CurriculumProblem = {
    problem: ProblemSummary;
    status: "locked" | "not_started" | "attempted" | "completed";
    recommended: boolean;
    prerequisite_problem_ids: number[];
};

export type CurriculumPool = {
    slug: string;
    name: string;
    tier: number | null;
    tier_name: string | null;
    optional: boolean;
    prerequisite_pool_slugs: string[];
    problems: CurriculumProblem[];
};

export function getCurriculum() {
    return apiRequest<CurriculumPool[]>("/api/curriculum");
}
