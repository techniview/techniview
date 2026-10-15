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
    total: number;
    items: Array<{
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

            const tags = new Map<string, CurriculumPool>();
            let offset = 0;
            while (true) {
                const response = await apiRequest<ProblemListResponse>(
                    `/api/problems?limit=100&offset=${offset}`,
                );
                response.items.forEach((problem) => {
                    problem.typed_tags
                        .filter((tag) => tag.kind === "problem_type")
                        .forEach((tag) => {
                            tags.set(tag.slug, {
                                slug: tag.slug,
                                name: tag.name,
                                kind: "problem_type",
                            });
                        });
                });
                offset += response.items.length;
                if (response.items.length === 0 || offset >= response.total) {
                    break;
                }
            }

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

export async function getAllClassAnalytics(courseId: number) {
    const items: ProblemAnalytics[] = [];
    while (true) {
        const page = await getClassAnalytics(
            courseId,
            `?limit=100&offset=${items.length}`,
        );
        items.push(...page.items);
        if (page.items.length === 0 || items.length >= page.total) {
            return items;
        }
    }
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
    withdrawn_at: string | null;
};

export type CourseList = {
    items: Course[];
    total: number;
    limit: number;
    offset: number;
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
            title: string;
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
    total: number;
    limit: number;
    offset: number;
};

export async function getActiveStaffCourse(): Promise<Course | null> {
    let offset = 0;
    let archivedCourse: Course | null = null;
    while (true) {
        const page = await apiRequest<CourseList>(
            `/api/courses?limit=100&offset=${offset}`,
        );
        for (const course of page.items) {
            if (course.withdrawn_at === null && course.membership_role !== "student") {
                if (course.archived_at === null) {
                    return course;
                }
                archivedCourse ??= course;
            }
        }
        offset += page.items.length;
        if (page.items.length === 0 || offset >= page.total) {
            return archivedCourse;
        }
    }
}

export async function getAllClassMembers(courseId: number) {
    const items: ClassMember[] = [];
    while (true) {
        const page = await apiRequest<MemberList>(
            `/api/courses/${courseId}/members?limit=200&offset=${items.length}`,
        );
        items.push(...page.items);
        if (page.items.length === 0 || items.length >= page.total) {
            return items;
        }
    }
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
