import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import "../pages/teacher/TeacherPages.css";
import "../pages/student/StudentPages.css";

export default function AppLayout() {
    return (
        <div className="app-layout">
            <Sidebar />

            <main className="page-content">
                <Outlet />
            </main>
        </div>
    );
}
