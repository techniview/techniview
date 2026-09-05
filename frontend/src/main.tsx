import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

const rootElement: HTMLElement | null = document.getElementById("root");
if (rootElement === null) {
    throw new Error("root element missing");
}

ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
        <App />
    </React.StrictMode>,
);
