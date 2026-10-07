import { apiRequest } from "./client";
import type {
    ClassAnalytics,
    ProblemAnalytics,
    StudentAnalytics,
} from "../types/analytics";

export function getStudentAnalytics() {
    return apiRequest<StudentAnalytics>("/api/me/analytics");
}

export function getClassAnalytics(courseId: number, query = "") {
    return apiRequest<ClassAnalytics>(
        `/api/courses/${courseId}/analytics/overview${query}`,
    );
}

export function getProblemAnalytics(courseId: number, problemId: number) {
    return apiRequest<ProblemAnalytics>(
        `/api/courses/${courseId}/analytics/problems/${problemId}`,
    );
}
