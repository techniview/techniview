import { useEffect, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { getActiveStaffCourse } from "../api/analytics";
import { useAuth } from "../auth/useAuth";
import BrandLogo from "./BrandLogo";
import SidebarIcon, { type SidebarIconName } from "./SidebarIcon";
import ThemeToggle from "./ThemeToggle";
import lightMark from "../assets/TechniView_Logo_No_Title.png";
import darkMark from "../assets/TechniView_Logo_No_Title_Dark.svg";

type NavigationItem = {
    label: string;
    to: string;
    icon: SidebarIconName;
};

const studentNavigation: NavigationItem[] = [
    { label: "My Classes", to: "/student/courses", icon: "classes" },
    { label: "Curriculum", to: "/student/curriculum", icon: "curriculum" },
    { label: "My Statistics", to: "/student/statistics", icon: "statistics" },
    { label: "All Problems", to: "/student/problems", icon: "problems" },
];

const professorNavigation: NavigationItem[] = [
    { label: "My Classes", to: "/teacher/classes", icon: "classes" },
    { label: "Overall Statistics", to: "/teacher/statistics", icon: "statistics" },
    { label: "Problems", to: "/teacher/problems", icon: "problems" },
];

function navigationForRole(role: "student" | "professor"): NavigationItem[] {
    return role === "professor" ? professorNavigation : studentNavigation;
}

export default function Sidebar({
    collapsed,
    onToggle,
}: {
    collapsed: boolean;
    onToggle: () => void;
}) {
    const { user, logout } = useAuth();
    const navigate = useNavigate();
    const [hasStaffCourse, setHasStaffCourse] = useState(false);

    useEffect(() => {
        if (user?.role !== "student") {
            return;
        }
        let isCurrent = true;
        void getActiveStaffCourse()
            .then((course) => {
                if (isCurrent) {
                    setHasStaffCourse(course !== null);
                }
            })
            .catch(() => {
                if (isCurrent) {
                    setHasStaffCourse(false);
                }
            });
        return () => {
            isCurrent = false;
        };
    }, [user?.id, user?.role]);

    if (user === null) {
        return null;
    }

    const navigation =
        user.role === "student" && hasStaffCourse
            ? [...studentNavigation, ...professorNavigation]
            : navigationForRole(user.role);

    async function handleLogout() {
        try {
            await logout();
            navigate("/login", { replace: true });
        } catch (error) {
            console.error("Logout failed.", error);
        }
    }

    return (
        <aside className="sidebar" aria-label="Primary navigation">
            <div className="sidebar-header">
                <NavLink className="sidebar-brand" to="/" aria-label="TechniView home">
                    <span className="sidebar-full-logo">
                        <BrandLogo />
                    </span>
                    <span className="sidebar-mark">
                        <img className="brand-logo-light" src={lightMark} alt="" />
                        <img className="brand-logo-dark" src={darkMark} alt="" />
                    </span>
                </NavLink>
                <p className="sidebar-user">{user.name}</p>
            </div>

            <nav className="sidebar-navigation">
                {navigation.map((item) => (
                    <NavLink
                        className={({ isActive }) =>
                            isActive
                                ? "sidebar-link sidebar-link-active"
                                : "sidebar-link"
                        }
                        key={item.to}
                        to={item.to}
                        end
                        aria-label={item.label}
                        title={collapsed ? item.label : undefined}
                    >
                        <SidebarIcon name={item.icon} />
                        <span className="sidebar-link-label">{item.label}</span>
                    </NavLink>
                ))}
            </nav>

            <div className="sidebar-logout-section">
                <button
                    aria-label="Log out"
                    className="sidebar-logout"
                    onClick={() => void handleLogout()}
                    title={collapsed ? "Log out" : undefined}
                    type="button"
                >
                    <SidebarIcon name="logout" />
                    <span className="sidebar-logout-label">Log out</span>
                </button>
            </div>

            <div className="sidebar-controls">
                <div className="sidebar-theme">
                    <ThemeToggle />
                </div>
                <button
                    aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                    aria-expanded={!collapsed}
                    className="sidebar-collapse"
                    onClick={onToggle}
                    title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                    type="button"
                >
                    <SidebarIcon name="collapse" />
                    <span className="sidebar-collapse-label">
                        {collapsed ? "Expand" : "Collapse"}
                    </span>
                </button>
            </div>
        </aside>
    );
}
