import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getAvailableProblems, type ProblemSummary } from "../../api/problems";
import { getCurriculum } from "../../api/curriculum";
import StudentProblemsPage from "./StudentProblemsPage";

vi.mock("../../api/problems", () => ({ getAvailableProblems: vi.fn() }));
vi.mock("../../api/curriculum", () => ({ getCurriculum: vi.fn() }));

function problem(id: number): ProblemSummary {
    return {
        id,
        title: `Problem ${id}`,
        difficulty: "easy",
        origin: "imported",
        state: "published",
        tags: [],
        typed_tags: [],
        source_category: null,
        available_assignment_item_id: null,
    };
}

describe("StudentProblemsPage", () => {
    afterEach(() => {
        cleanup();
        vi.clearAllMocks();
    });

    it("requests one page at a time and shows the next page", async () => {
        vi.mocked(getCurriculum).mockResolvedValue([]);
        vi.mocked(getAvailableProblems).mockImplementation(async (offset, limit) => ({
            items: offset === 0 ? [problem(1)] : [problem(26)],
            total: 50,
            limit: limit ?? 25,
            offset: offset ?? 0,
        }));
        render(
            <MemoryRouter initialEntries={["/student/problems"]}>
                <Routes>
                    <Route path="/student/problems" element={<StudentProblemsPage />} />
                </Routes>
            </MemoryRouter>,
        );

        expect(await screen.findByText("Problem 1")).toBeTruthy();
        expect(getAvailableProblems).toHaveBeenCalledWith(0, 25, {
            search: "",
            difficulty: "",
            tag: "",
            sort: "trail",
        });
        fireEvent.click(screen.getByRole("button", { name: "Next" }));
        expect(await screen.findByText("Problem 26")).toBeTruthy();
        expect(getAvailableProblems).toHaveBeenCalledWith(25, 25, {
            search: "",
            difficulty: "",
            tag: "",
            sort: "trail",
        });
        expect(screen.getByText("Page 2 of 2")).toBeTruthy();
    });
});
