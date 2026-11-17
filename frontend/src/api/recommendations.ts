import { apiRequest } from "./client";
import type { ProblemSummary } from "./problems";

export type Recommendation = {
    rank: number;
    reason: "struggling_area" | "next_trail_step" | "low_completion_coverage";
    pool_slug: string;
    pool_name: string;
    problem: ProblemSummary;
};

export function getRecommendations() {
    return apiRequest<{ items: Recommendation[] }>("/api/recommendations");
}
