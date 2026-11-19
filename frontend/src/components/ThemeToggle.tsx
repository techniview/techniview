import { applyTheme, useTheme } from "../theme";

export default function ThemeToggle() {
    const theme = useTheme();

    function toggleTheme() {
        const nextTheme = theme === "dark" ? "light" : "dark";
        applyTheme(nextTheme, true);
    }

    return (
        <button
            aria-checked={theme === "dark"}
            aria-label="Dark mode"
            className="theme-toggle"
            onClick={toggleTheme}
            role="switch"
            type="button"
        >
            <span aria-hidden="true" className="theme-toggle-thumb" />
            <svg
                aria-hidden="true"
                className="theme-toggle-icon theme-toggle-sun"
                fill="none"
                viewBox="0 0 24 24"
            >
                <circle cx="12" cy="12" r="4" />
                <path d="M12 2v2m0 16v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42" />
            </svg>
            <svg
                aria-hidden="true"
                className="theme-toggle-icon theme-toggle-moon"
                fill="none"
                viewBox="0 0 24 24"
            >
                <path d="M20.5 14.1A8.5 8.5 0 0 1 9.9 3.5 8.5 8.5 0 1 0 20.5 14.1Z" />
            </svg>
        </button>
    );
}
