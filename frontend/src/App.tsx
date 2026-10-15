import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthProvider";
import ProtectedRoute from "./auth/ProtectedRoute";
import AppLayout from "./components/AppLayout";
import LoadingState from "./components/LoadingState";
import LoginPage from "./pages/LoginPage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import JoinPage from "./pages/JoinPage";
import ProblemPage from "./pages/ProblemPage";
import ResetPasswordPage from "./pages/ResetPasswordPage";
import VerifyEmailPage from "./pages/VerifyEmailPage";
import StudentStatisticsPage from "./pages/student/StudentStatisticsPage";
import StudentProblemsPage from "./pages/student/StudentProblemsPage";
import StudentCoursePage from "./pages/student/StudentCoursePage";
import StudentCoursesPage from "./pages/student/StudentCoursesPage";
import StudentCurriculumPage from "./pages/student/StudentCurriculumPage";
import TeacherClassPage from "./pages/teacher/TeacherClassPage";
import TeacherProblemPage from "./pages/teacher/TeacherProblemPage";
import TeacherOverallStatsPage from "./pages/teacher/TeacherOverallStatsPage";
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

export default function App() {
    return (
        <BrowserRouter>
            <AuthProvider>
                <Routes>
                    <Route path="/login" element={<LoginPage />} />
                    <Route path="/forgot-password" element={<ForgotPasswordPage />} />
                    <Route path="/reset-password" element={<ResetPasswordPage />} />
                    <Route path="/verify-email" element={<VerifyEmailPage />} />
                    <Route path="/join/:token" element={<JoinPage />} />

                    <Route element={<ProtectedRoute />}>
                        <Route element={<AppLayout />}>
                            <Route
                                path="/student/statistics"
                                element={<StudentStatisticsPage />}
                            />
                            <Route
                                path="/student/problems"
                                element={<StudentProblemsPage />}
                            />
                            <Route
                                path="/student/curriculum"
                                element={<StudentCurriculumPage />}
                            />
                            <Route
                                path="/student/courses/:courseId"
                                element={<StudentCoursePage />}
                            />
                            <Route
                                path="/student/courses"
                                element={<StudentCoursesPage />}
                            />

                            <Route
                                path="/student/problems/:problemId"
                                element={<ProblemPage />}
                            />

                            <Route
                                path="/teacher/class"
                                element={<TeacherClassPage />}
                            />
                            <Route
                                path="/teacher/statistics"
                                element={<TeacherOverallStatsPage />}
                            />
                            <Route
                                path="/teacher/problems"
                                element={<TeacherProblemPage />}
                            />
                            <Route
                                path="/teacher/problems/:problemId"
                                element={<ProblemPage />}
                            />
                        </Route>
                    </Route>

                    <Route path="/" element={<RoleHomeRedirect />} />
                    <Route path="*" element={<RoleHomeRedirect />} />
                </Routes>
            </AuthProvider>
        </BrowserRouter>
    );
}
