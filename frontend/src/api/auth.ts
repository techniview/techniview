import { apiRequest } from "./client";
import type { User } from "../types/auth";

export function getCurrentUser() {
    return apiRequest<User>("/api/auth/me");
}

export function login(email: string, password: string) {
    return apiRequest<User>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
    });
}

export function logout() {
    return apiRequest<undefined>("/api/auth/logout", {
        method: "POST",
    });
}

export function requestPasswordRecovery(email: string) {
    return apiRequest<{ message: string }>("/api/auth/password-recovery", {
        method: "POST",
        body: JSON.stringify({ email }),
    });
}
export function resetPassword(
    token: string,
    password: string,
    passwordConfirm: string,
) {
    return apiRequest<undefined>("/api/auth/password-reset", {
        method: "POST",
        body: JSON.stringify({ token, password, password_confirm: passwordConfirm }),
    });
}
export function verifyEmail(token: string) {
    return apiRequest<User>("/api/auth/verify-email", {
        method: "POST",
        body: JSON.stringify({ token }),
    });
}

export type JoinPreview = {
    course_id: number;
    name: string;
    description: string | null;
    joinable: boolean;
};

export function getJoinPreview(token: string) {
    return apiRequest<JoinPreview>(`/api/join/${encodeURIComponent(token)}`);
}

export function joinSignup(
    token: string,
    name: string,
    email: string,
    password: string,
    passwordConfirm: string,
) {
    return apiRequest<{ message: string }>(
        `/api/join/${encodeURIComponent(token)}/signup`,
        {
            method: "POST",
            body: JSON.stringify({
                name,
                email,
                password,
                password_confirm: passwordConfirm,
            }),
        },
    );
}

export function joinLogin(token: string, email: string, password: string) {
    return apiRequest<User | { message: string }>(
        `/api/join/${encodeURIComponent(token)}/login`,
        { method: "POST", body: JSON.stringify({ email, password }) },
    );
}
