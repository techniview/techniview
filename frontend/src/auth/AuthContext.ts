import { createContext } from "react";
import type { User } from "../types/auth";

export type AuthContextValue = {
    user: User | null;
    isLoading: boolean;
    logout: () => Promise<void>;
    refreshUser: () => Promise<void>;
};

export const AuthContext = createContext<AuthContextValue | null>(null);
