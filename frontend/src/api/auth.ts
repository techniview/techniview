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
