import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { applyTheme, type Theme } from "./theme";
import "./components/AppBrand.css";

const savedTheme = localStorage.getItem("techniview-theme");
const theme: Theme =
    savedTheme === "light" || savedTheme === "dark"
        ? savedTheme
        : window.matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light";
applyTheme(theme);

const rootElement: HTMLElement | null = document.getElementById("root");
if (rootElement === null) {
    throw new Error("root element missing");
}

ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
        <App />
    </React.StrictMode>,
);
