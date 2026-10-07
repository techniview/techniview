import { Navigate, Outlet, useLocation } from "react-router-dom";
import LoadingState from "../components/LoadingState";
import { useAuth } from "./useAuth";
import type { UserRole } from "../types/auth";

type ProtectedRouteProps = {
    allowedRoles?: UserRole[];
};

function defaultRouteForRole(role: UserRole): string {
    return role === "professor" ? "/teacher/class" : "/student/statistics";
}

export default function ProtectedRoute({ allowedRoles }: ProtectedRouteProps) {
    const { user, isLoading } = useAuth();
    const location = useLocation();

    if (isLoading) {
        return <LoadingState message="Checking your session..." />;
    }

    if (user === null) {
        return <Navigate replace state={{ from: location }} to="/login" />;
    }

    if (allowedRoles && !allowedRoles.includes(user.role)) {
        return <Navigate replace to={defaultRouteForRole(user.role)} />;
    }

    return <Outlet />;
}
