const API_URL =
    import.meta.env.VITE_API_URL ??
    (import.meta.env.PROD ? "" : "http://localhost:8000");

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
        throw new Error(`Request failed with status ${response.status}`);
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
