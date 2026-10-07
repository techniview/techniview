import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
    it("renders techniview", async () => {
        render(<App />);
        expect(
            await screen.findByRole("heading", { name: /techniview/i }),
        ).not.toBeNull();
    });
});
