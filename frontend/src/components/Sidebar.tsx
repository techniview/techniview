import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";

type NavigationItem = {
    label: string;
    to: string;
};

const studentNavigation: NavigationItem[] = [
    { label: "My Statistics", to: "/student/statistics" },
];

const professorNavigation: NavigationItem[] = [
    { label: "Class Overview", to: "/teacher/class" },
    { label: "Problems", to: "/teacher/problems" },
];

function navigationForRole(role: "student" | "professor"): NavigationItem[] {
    return role === "professor" ? professorNavigation : studentNavigation;
}

export default function Sidebar() {
    const { user, logout } = useAuth();
    const navigate = useNavigate();

    if (user === null) {
        return null;
    }

    const navigation = navigationForRole(user.role);

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
                <NavLink className="sidebar-brand" to="/">
                    TechniView
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
                    >
                        {item.label}
                    </NavLink>
                ))}
            </nav>

            <button
                className="sidebar-logout"
                onClick={() => void handleLogout()}
                type="button"
            >
                Log out
            </button>
        </aside>
    );
}
