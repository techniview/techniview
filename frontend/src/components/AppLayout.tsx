import { useState } from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import "../pages/teacher/TeacherPages.css";
import "../pages/student/StudentPages.css";

export default function AppLayout() {
    const [sidebarCollapsed, setSidebarCollapsed] = useState(
        () => localStorage.getItem("techniview-sidebar-collapsed") === "true",
    );

    function toggleSidebar() {
        setSidebarCollapsed((collapsed) => {
            localStorage.setItem("techniview-sidebar-collapsed", String(!collapsed));
            return !collapsed;
        });
    }

    return (
        <div
            className="app-layout"
            data-sidebar-collapsed={sidebarCollapsed ? "true" : undefined}
        >
            <Sidebar collapsed={sidebarCollapsed} onToggle={toggleSidebar} />
            <div className="app-main">
                <main className="page-content">
                    <Outlet />
                </main>
            </div>
        </div>
    );
}
