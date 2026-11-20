const API_URL =
    import.meta.env.VITE_API_URL ??
    (import.meta.env.PROD
        ? import.meta.env.BASE_URL.replace(/\/$/, "")
        : "http://localhost:8000");

export class ApiRequestError extends Error {
    constructor(
        message: string,
        readonly status: number,
        readonly code: string | null,
    ) {
        super(message);
        this.name = "ApiRequestError";
    }
}

export async function apiRequest<T>(path: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${API_URL}${path}`, {
        ...options,
        credentials: "include",
        headers: {
            "Content-Type": "application/json",
            ...options?.headers,
        },
    });

    if (!response.ok) {
        const body: unknown = await response.json().catch(() => null);
        const error =
            body && typeof body === "object" && "error" in body ? body.error : null;
        const message =
            error &&
            typeof error === "object" &&
            "message" in error &&
            typeof error.message === "string"
                ? error.message
                : `Request failed with status ${response.status}`;
        const code =
            error &&
            typeof error === "object" &&
            "code" in error &&
            typeof error.code === "string"
                ? error.code
                : null;
        throw new ApiRequestError(message, response.status, code);
    }

    if (response.status === 204) {
        return undefined as T;
    }

    return response.json() as Promise<T>;
}

export async function apiText(path: string): Promise<string> {
    const response = await fetch(`${API_URL}${path}`, { credentials: "include" });
    if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
    }
    return response.text();
}
