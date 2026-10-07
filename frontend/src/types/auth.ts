export type UserRole = "student" | "professor";

export type User = {
    id: number;
    name: string;
    email: string;
    role: UserRole;
};
