export type SidebarIconName =
    "classes" | "curriculum" | "statistics" | "problems" | "collapse" | "logout";

export default function SidebarIcon({ name }: { name: SidebarIconName }) {
    const paths = {
        classes: (
            <>
                <path d="M3 7.5 12 3l9 4.5v11L12 23l-9-4.5z" />
                <path d="M3 7.5 12 12l9-4.5M12 12v11" />
            </>
        ),
        curriculum: (
            <>
                <circle cx="5" cy="5" r="2" />
                <circle cx="19" cy="19" r="2" />
                <path d="M7 5h8a4 4 0 0 1 0 8H9a4 4 0 0 0 0 6h8" />
            </>
        ),
        statistics: (
            <>
                <path d="M3 21h18M5 17v-5M10 17V8M15 17V4M20 17v-7" />
            </>
        ),
        problems: (
            <>
                <path d="M8 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h3M16 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3" />
                <path d="m10 8-4 4 4 4m4-8 4 4-4 4" />
            </>
        ),
        collapse: (
            <>
                <rect x="3" y="4" width="18" height="16" rx="2" />
                <path d="M9 4v16m7-11-3 3 3 3" />
            </>
        ),
        logout: (
            <>
                <path d="M11 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h5" />
                <path d="m16 8 4 4-4 4m4-4H10" />
            </>
        ),
    } satisfies Record<SidebarIconName, React.ReactNode>;

    return (
        <svg
            aria-hidden="true"
            className="sidebar-icon"
            fill="none"
            viewBox="0 0 24 24"
        >
            {paths[name]}
        </svg>
    );
}
