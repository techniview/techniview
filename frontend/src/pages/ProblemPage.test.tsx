import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ProblemPage from "./ProblemPage";
import { createSubmission, getSubmissionComplexity } from "../api/submissions";
import { getProblem, startProblem } from "../api/problems";

vi.mock("@monaco-editor/react", () => ({
    default: ({
        value,
        onChange,
    }: {
        value: string;
        onChange: (v: string) => void;
    }) => (
        <textarea
            aria-label="Solution code"
            value={value}
            onChange={(event) => onChange(event.target.value)}
        />
    ),
}));

vi.mock("../api/problems", () => ({
    getProblem: vi.fn(),
    startProblem: vi.fn(),
    runPublicCases: vi.fn(),
}));

vi.mock("../api/submissions", () => ({
    createSubmission: vi.fn(),
    getSubmission: vi.fn(),
    getSubmissionComplexity: vi.fn(),
}));

const problem = {
    id: 11,
    title: "Sum a List",
    difficulty: "easy" as const,
    origin: "imported" as const,
    state: "published" as const,
    tags: [],
    prompt: "Return the sum of the values.",
    execution_mode: "call_based" as const,
    function_name: "sum_list",
    starter_code: "def sum_list(values):\n    return sum(values)",
    public_tests: [],
    test_count: 1,
    attribution: null,
    license: null,
    assignment_contexts: [],
};

const submission = {
    id: 29,
    problem_id: 11,
    assignment_item_id: null,
    status: "passed",
    failure_code: null,
    failure_message: null,
    retryable: false,
    phase: "complete" as const,
    done: true,
    is_practice_run: false,
    score: 1,
    is_late: false,
    late_approved: false,
    passed_count: 1,
    test_count: 1,
    public_results: [],
    primary_error: null,
    python_exception_type: null,
    submitted_at: "2026-10-28T12:00:00Z",
    completed_at: "2026-10-28T12:00:01Z",
    poll_url: "/api/submissions/29",
};

function renderProblemPage() {
    return render(
        <MemoryRouter initialEntries={["/student/problems/11"]}>
            <Routes>
                <Route path="/student/problems/:problemId" element={<ProblemPage />} />
            </Routes>
        </MemoryRouter>,
    );
}

describe("ProblemPage complexity estimate", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(getProblem).mockResolvedValue(problem);
        vi.mocked(startProblem).mockResolvedValue(undefined);
        vi.mocked(createSubmission).mockResolvedValue(submission);
        vi.stubGlobal("crypto", { randomUUID: () => "request-key" });
    });

    it("shows the estimate after grading completes", async () => {
        let resolveAnalysis:
            | ((value: Awaited<ReturnType<typeof getSubmissionComplexity>>) => void)
            | undefined;
        vi.mocked(getSubmissionComplexity).mockImplementation(
            () =>
                new Promise((resolve) => {
                    resolveAnalysis = resolve;
                }),
        );
        renderProblemPage();

        fireEvent.click(
            await screen.findByRole("button", { name: "Submit for grading" }),
        );

        expect(await screen.findByText(/Accepted/)).toBeTruthy();
        expect(await screen.findByText("Analyzing your solution...")).toBeTruthy();
        await act(async () => {
            resolveAnalysis?.({
                status: "complete",
                time_complexity: "O(n)",
                space_complexity: "O(1)",
                model: "qwen3.8:27b",
                prompt_version: "1",
                error_code: null,
                analyzed_at: "2026-10-28T12:00:02Z",
            });
        });
        expect(await screen.findByText("O(n)")).toBeTruthy();
        expect(await screen.findByText("O(1)")).toBeTruthy();
        expect(getSubmissionComplexity).toHaveBeenCalledWith(29);
        expect(screen.getByText(/does not affect grading/i)).toBeTruthy();
    });

    it("keeps grading feedback visible when complexity analysis is disabled", async () => {
        vi.mocked(getSubmissionComplexity).mockResolvedValue({
            status: "disabled",
            time_complexity: null,
            space_complexity: null,
            model: "qwen3.8:27b",
            prompt_version: "1",
            error_code: null,
            analyzed_at: null,
        });
        renderProblemPage();

        fireEvent.click(
            await screen.findByRole("button", { name: "Submit for grading" }),
        );

        expect(await screen.findByText(/Accepted/)).toBeTruthy();
        expect(
            await screen.findByText("Complexity estimate unavailable."),
        ).toBeTruthy();
        expect(createSubmission).toHaveBeenCalledOnce();
    });
});
