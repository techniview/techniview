import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
    it("renders techniview", () => {
        render(<App />);
        expect(screen.getByText("techniview")).not.toBeNull();
    });
});
