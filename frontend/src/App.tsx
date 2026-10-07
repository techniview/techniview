import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthProvider";
import ProtectedRoute from "./auth/ProtectedRoute";
import AppLayout from "./components/AppLayout";
import LoadingState from "./components/LoadingState";
import LoginPage from "./pages/LoginPage";
import { useAuth } from "./auth/useAuth";

function RoleHomeRedirect() {
    const { user, isLoading } = useAuth();

    if (isLoading) {
        return <LoadingState message="Checking your session..." />;
    }

    if (user === null) {
        return <Navigate replace to="/login" />;
    }

    return (
        <Navigate
            replace
            to={user.role === "professor" ? "/teacher/class" : "/student/statistics"}
        />
    );
}

function StudentStatisticsPlaceholder() {
    return <h1>Student Statistics</h1>;
}

function TeacherClassPlaceholder() {
    return <h1>Class Overview</h1>;
}

function TeacherProblemsPlaceholder() {
    return <h1>Problems</h1>;
}

function TeacherProblemDetailPlaceholder() {
    return <h1>Problem Details</h1>;
}

export default function App() {
    return (
        <BrowserRouter>
            <AuthProvider>
                <Routes>
                    <Route path="/login" element={<LoginPage />} />

                    <Route element={<ProtectedRoute />}>
                        <Route element={<AppLayout />}>
                            <Route
                                path="/student/statistics"
                                element={<StudentStatisticsPlaceholder />}
                            />

                            <Route
                                element={
                                    <ProtectedRoute allowedRoles={["professor"]} />
                                }
                            >
                                <Route
                                    path="/teacher/class"
                                    element={<TeacherClassPlaceholder />}
                                />
                                <Route
                                    path="/teacher/problems"
                                    element={<TeacherProblemsPlaceholder />}
                                />
                                <Route
                                    path="/teacher/problems/:problemId"
                                    element={<TeacherProblemDetailPlaceholder />}
                                />
                            </Route>
                        </Route>
                    </Route>

                    <Route path="/" element={<RoleHomeRedirect />} />
                    <Route path="*" element={<RoleHomeRedirect />} />
                </Routes>
            </AuthProvider>
        </BrowserRouter>
    );
}
