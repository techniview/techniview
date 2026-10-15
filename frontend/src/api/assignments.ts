import { apiRequest } from "./client";
import type { Assignment, AssignmentList } from "./analytics";

export type AssignmentItemInput = {
    problem_id: number;
    points?: number;
    submission_limit?: number | null;
};
export type AssignmentEdit = {
    title?: string;
    description?: string | null;
    available_at?: string | null;
    due_at?: string | null;
    items?: AssignmentItemInput[];
    recipient_mode?: "all" | "selected";
    selected_membership_ids?: number[];
};
export type AssignmentCreate = AssignmentEdit & { title: string } & (
        | { question_set_id: number; items?: never }
        | { items: AssignmentItemInput[]; question_set_id?: never }
    );
export type Page<T> = { items: T[]; total: number; limit: number; offset: number };
export type Grade = {
    student_id: number;
    email: string;
    assignment_id: number;
    assignment_item_id: number;
    problem_id: number;
    points_possible: number;
    best_score: number;
    points_earned: number;
    valid_attempts: number;
    passed: boolean;
    withdrawn: boolean;
};
export type AssignmentAudit = {
    id: number;
    actor_membership_id: number;
    action: string;
    before: Record<string, unknown>;
    after: Record<string, unknown>;
    created_at: string;
};
const path = (courseId: number, assignmentId?: number) =>
    `/api/courses/${courseId}/assignments${assignmentId === undefined ? "" : `/${assignmentId}`}`;

export function listAssignments(courseId: number, limit = 50, offset = 0) {
    return apiRequest<AssignmentList>(
        `${path(courseId)}?limit=${limit}&offset=${offset}`,
    );
}
export function getAssignment(courseId: number, assignmentId: number) {
    return apiRequest<Assignment>(path(courseId, assignmentId));
}
export function createAssignment(courseId: number, body: AssignmentCreate) {
    return apiRequest<Assignment>(path(courseId), {
        method: "POST",
        body: JSON.stringify(body),
    });
}
export function editAssignment(
    courseId: number,
    assignmentId: number,
    body: AssignmentEdit,
) {
    return apiRequest<Assignment>(path(courseId, assignmentId), {
        method: "PATCH",
        body: JSON.stringify(body),
    });
}
export function publishAssignment(courseId: number, assignmentId: number) {
    return apiRequest<Assignment>(`${path(courseId, assignmentId)}/publish`, {
        method: "POST",
    });
}
export function archiveAssignment(courseId: number, assignmentId: number) {
    return apiRequest<Assignment>(`${path(courseId, assignmentId)}/archive`, {
        method: "POST",
    });
}
export function getAssignmentRecipients(courseId: number, assignmentId: number) {
    return apiRequest<{
        items: Array<{ membership_id: number; removed_at: string | null }>;
    }>(`${path(courseId, assignmentId)}/recipients`);
}
export function changeAssignmentRecipients(
    courseId: number,
    assignmentId: number,
    add: number[],
    remove: number[],
) {
    return apiRequest<undefined>(`${path(courseId, assignmentId)}/recipients`, {
        method: "POST",
        body: JSON.stringify({
            add_membership_ids: add,
            remove_membership_ids: remove,
        }),
    });
}
export function getAssignmentGrades(
    courseId: number,
    assignmentId: number,
    limit = 50,
    offset = 0,
) {
    return apiRequest<Page<Grade>>(
        `${path(courseId, assignmentId)}/grades?limit=${limit}&offset=${offset}`,
    );
}
export function getAssignmentAudit(
    courseId: number,
    assignmentId: number,
    limit = 50,
    offset = 0,
) {
    return apiRequest<Page<AssignmentAudit>>(
        `${path(courseId, assignmentId)}/audit?limit=${limit}&offset=${offset}`,
    );
}
