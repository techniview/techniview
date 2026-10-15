import { apiRequest, apiText } from "./client";
import type {
    ClassAnalytics,
    ProblemAnalytics,
    StudentProblemAnalytics,
    StudentAnalytics,
} from "../types/analytics";

export type CurriculumPool = {
    slug: string;
    name: string;
    kind: "technique" | "problem_type";
};

type ProblemListResponse = {
    items: Array<{
        tags: string[];
        typed_tags: Array<{
            name: string;
            slug: string;
            kind: "general" | "technique" | "problem_type";
        }>;
    }>;
};

export function getStudentAnalytics(
    difficulty: string | null = null,
    tag: string | null = null,
    options: {
        scope?: "all" | "practice" | "assignments";
        course_id?: number;
        assignment_id?: number;
        limit?: number;
        offset?: number;
    } = {},
) {
    const params = new URLSearchParams();
    if (difficulty) {
        params.set("difficulty", difficulty);
    }
    if (tag) {
        params.set("tag", tag);
    }

    Object.entries(options).forEach(([key, value]) => params.set(key, String(value)));
    const query = params.toString();
    return apiRequest<StudentAnalytics>(`/api/me/analytics${query ? `?${query}` : ""}`);
}

export function getProblemTypes() {
    return apiRequest<CurriculumPool[]>("/api/curriculum?kind=problem_type").then(
        async (pools) => {
            if (pools.length > 0) {
                return pools;
            }

            const response = await apiRequest<ProblemListResponse>(
                "/api/problems?limit=100",
            );
            const tags = new Map<string, CurriculumPool>();
            response.items.forEach((problem) => {
                const typedTags = problem.typed_tags;
                if (typedTags.length > 0) {
                    typedTags.forEach((tag) => {
                        tags.set(tag.slug, {
                            slug: tag.slug,
                            name: tag.name,
                            kind: "problem_type",
                        });
                    });
                    return;
                }

                problem.tags.forEach((tag) => {
                    tags.set(tag, {
                        slug: tag,
                        name: tag.replace(/-/g, " "),
                        kind: "problem_type",
                    });
                });
            });

            return [...tags.values()].sort((left, right) =>
                left.name.localeCompare(right.name),
            );
        },
    );
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

export type Course = {
    id: number;
    name: string;
    description: string | null;
    timezone: string;
    archived_at: string | null;
    membership_role: "student" | "instructor" | "ta";
};

export type CourseList = {
    items: Course[];
};

export type Assignment = {
    id: number;
    course_id: number;
    title: string;
    description: string | null;
    state: "draft" | "published" | "archived";
    available_at: string | null;
    due_at: string | null;
    items: Array<{
        id: number;
        item_order: number;
        points: string;
        submission_limit: number | null;
        problem: {
            id: number;
        };
    }>;
};

export type AssignmentList = {
    total: number;
    limit: number;
    offset: number;
    items: Assignment[];
};

export type ClassMember = {
    id: number;
    user_id: number;
    name: string;
    email: string;
    role: "student" | "instructor" | "ta";
    withdrawn_at: string | null;
};

export type MemberList = {
    items: ClassMember[];
};

export function getTeacherCourses() {
    return apiRequest<CourseList>("/api/courses");
}

export function getStudentAssignments(courseId: number, offset = 0) {
    return apiRequest<AssignmentList>(
        `/api/courses/${courseId}/assignments?limit=100&offset=${offset}`,
    );
}

export function getClassMembers(courseId: number) {
    return apiRequest<MemberList>(`/api/courses/${courseId}/members`);
}

export function getGradeCsv(courseId: number, assignmentId?: number) {
    const query = assignmentId === undefined ? "" : `?assignment_id=${assignmentId}`;
    return apiText(`/api/courses/${courseId}/exports/grades.csv${query}`);
}

export function getResearchCsv(
    courseId: number,
    assignmentId: number,
    publicationKey: string,
) {
    const params = new URLSearchParams({
        assignment_id: String(assignmentId),
        publication_key: publicationKey,
    });
    return apiText(`/api/courses/${courseId}/exports/research.csv?${params}`);
}

export function getStudentProblemAnalytics(
    courseId: number,
    studentId: number,
    problemId: number,
) {
    return apiRequest<StudentProblemAnalytics>(
        `/api/courses/${courseId}/analytics/students/${studentId}/problems/${problemId}`,
    );
}
