import {
    useCallback,
    useEffect,
    useMemo,
    useState,
    type PropsWithChildren,
} from "react";
import { getCurrentUser, logout as logoutUser } from "../api/auth";
import { AuthContext } from "./AuthContext";
import type { User } from "../types/auth";

export function AuthProvider({ children }: PropsWithChildren) {
    const [user, setUser] = useState<User | null>(null);
    const [isLoading, setIsLoading] = useState(true);

    const refreshUser = useCallback(async () => {
        try {
            setUser(await getCurrentUser());
        } catch {
            setUser(null);
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        void refreshUser();
    }, [refreshUser]);

    const logout = useCallback(async () => {
        await logoutUser();
        setUser(null);
    }, []);

    const value = useMemo(
        () => ({ user, isLoading, logout, refreshUser }),
        [isLoading, logout, refreshUser, user],
    );

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
