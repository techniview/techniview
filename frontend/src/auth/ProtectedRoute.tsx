import { Navigate, Outlet, useLocation } from "react-router-dom";
import LoadingState from "../components/LoadingState";
import { useAuth } from "./useAuth";

export default function ProtectedRoute() {
    const { user, isLoading } = useAuth();
    const location = useLocation();

    if (isLoading) {
        return <LoadingState message="Checking your session..." />;
    }

    if (user === null) {
        return <Navigate replace state={{ from: location }} to="/login" />;
    }

    return <Outlet />;
}
