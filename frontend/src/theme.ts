import { useSyncExternalStore } from "react";
import lightLogo from "./assets/TechniView_Logo_No_Title.png";
import darkFavicon from "./assets/TechniView_Favicon_Dark.png";

export type Theme = "light" | "dark";

function getTheme(): Theme {
    return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

function subscribeTheme(callback: () => void) {
    window.addEventListener("techniview-theme-change", callback);
    return () => window.removeEventListener("techniview-theme-change", callback);
}

export function useTheme() {
    return useSyncExternalStore(subscribeTheme, getTheme);
}

export function applyTheme(theme: Theme, persist = false) {
    document.documentElement.dataset.theme = theme;
    window.dispatchEvent(new Event("techniview-theme-change"));

    const favicon = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
    if (favicon) {
        favicon.href = theme === "dark" ? darkFavicon : lightLogo;
        favicon.type = "image/png";
    }

    if (persist) {
        localStorage.setItem("techniview-theme", theme);
    }
}
