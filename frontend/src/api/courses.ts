import { apiRequest } from "./client";
import type { Course, CourseList, MemberList, ClassMember } from "./analytics";
import type { Page } from "./assignments";
import type { User } from "../types/auth";

export type CourseInput = {
    name: string;
    description?: string | null;
    timezone?: string;
};
export type Enrollment = {
    id: number;
    email: string;
    name: string;
    created_at: string;
};
export type Message = { message: string };

export function listCourses(limit = 50, offset = 0) {
    return apiRequest<CourseList>(`/api/courses?limit=${limit}&offset=${offset}`);
}
export function getCourse(courseId: number) {
    return apiRequest<Course>(`/api/courses/${courseId}`);
}
export function createCourse(body: CourseInput) {
    return apiRequest<{ course: Course; join_token: string }>("/api/courses", {
        method: "POST",
        body: JSON.stringify(body),
    });
}
export function updateCourse(courseId: number, body: CourseInput) {
    return apiRequest<Course>(`/api/courses/${courseId}`, {
        method: "PUT",
        body: JSON.stringify(body),
    });
}
export function archiveCourse(courseId: number) {
    return apiRequest<Course>(`/api/courses/${courseId}/archive`, { method: "POST" });
}
export function rotateJoinLink(courseId: number) {
    return apiRequest<{ join_token: string }>(`/api/courses/${courseId}/join-link`, {
        method: "POST",
    });
}
export function importEnrollments(courseId: number, csv: string) {
    return apiRequest<{ enrolled: number; pending_signup: number }>(
        `/api/courses/${courseId}/enrollments/import`,
        { method: "POST", body: JSON.stringify({ csv }) },
    );
}
export function listEnrollments(courseId: number, limit = 50, offset = 0) {
    return apiRequest<Page<Enrollment>>(
        `/api/courses/${courseId}/enrollments?limit=${limit}&offset=${offset}`,
    );
}
export function deleteEnrollment(courseId: number, enrollmentId: number) {
    return apiRequest<undefined>(
        `/api/courses/${courseId}/enrollments/${enrollmentId}`,
        { method: "DELETE" },
    );
}
export function listCourseMembers(courseId: number, limit = 50, offset = 0) {
    return apiRequest<MemberList>(
        `/api/courses/${courseId}/members?limit=${limit}&offset=${offset}`,
    );
}
export function changeMemberRole(
    courseId: number,
    membershipId: number,
    role: "student" | "ta",
) {
    return apiRequest<ClassMember>(`/api/courses/${courseId}/members/${membershipId}`, {
        method: "PATCH",
        body: JSON.stringify({ role }),
    });
}
export function withdrawMember(courseId: number, membershipId: number) {
    return apiRequest<undefined>(`/api/courses/${courseId}/members/${membershipId}`, {
        method: "DELETE",
    });
}
export function joinSignup(
    token: string,
    body: { name: string; email: string; password: string; password_confirm: string },
) {
    return apiRequest<Message>(`/api/join/${encodeURIComponent(token)}/signup`, {
        method: "POST",
        body: JSON.stringify(body),
    });
}
export function joinLogin(token: string, email: string, password: string) {
    return apiRequest<User | Message>(`/api/join/${encodeURIComponent(token)}/login`, {
        method: "POST",
        body: JSON.stringify({ email, password }),
    });
}

export function getJoinPreview(token: string) {
    return apiRequest<{
        course_id: number;
        name: string;
        description: string | null;
        joinable: boolean;
    }>(`/api/join/${encodeURIComponent(token)}`);
}
