import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        host: "0.0.0.0",
        proxy: {
            "/api": "http://backend:8000",
        },
    },
    test: {
        environment: "jsdom",
    },
});
