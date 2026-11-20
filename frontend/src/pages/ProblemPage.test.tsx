import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ProblemPage from "./ProblemPage";
import { createSubmission, getSubmissionComplexity } from "../api/submissions";
import { getProblem, startProblem } from "../api/problems";
import { ApiRequestError } from "../api/client";

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
    started_at: "2026-10-28T12:00:00.500Z",
    completed_at: "2026-10-28T12:00:01Z",
    wait_seconds: 0.5,
    execution_seconds: 0.5,
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
    afterEach(() => {
        cleanup();
        vi.unstubAllGlobals();
    });

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
        vi.mocked(createSubmission).mockResolvedValue({
            ...submission,
            passed_count: 39,
            test_count: 39,
            public_results: [
                {
                    case_order: 1,
                    status_id: 3,
                    phase: "complete",
                    friendly_message: "Accepted. Nice work!",
                    input: "",
                    expected_output: "",
                    stdout: "true",
                    stderr: null,
                    compile_output: null,
                    execution_time_ms: null,
                    memory_kb: null,
                },
            ],
        });
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

        expect(await screen.findByText("Accepted — 39/39 tests passed.")).toBeTruthy();
        expect(
            await screen.findByText(
                "AI complexity estimates are not enabled for this deployment.",
            ),
        ).toBeTruthy();
        expect(screen.getByText(/Showing details for 1 public test/)).toBeTruthy();
        expect(
            screen.getByText(/Private tests count toward the result above/),
        ).toBeTruthy();
        expect(createSubmission).toHaveBeenCalledOnce();
    });

    it("submits when randomUUID is unavailable in a nonsecure browser context", async () => {
        vi.stubGlobal("crypto", {
            getRandomValues: (bytes: Uint8Array) => bytes.fill(7),
        });
        vi.mocked(getSubmissionComplexity).mockResolvedValue({
            status: "disabled",
            time_complexity: null,
            space_complexity: null,
            model: "",
            prompt_version: "",
            error_code: null,
            analyzed_at: null,
        });
        renderProblemPage();

        fireEvent.click(
            await screen.findByRole("button", { name: "Submit for grading" }),
        );

        expect(await screen.findByText(/Accepted/)).toBeTruthy();
        expect(vi.mocked(createSubmission).mock.calls[0]?.[2]).toMatch(
            /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
        );
    });

    it("shows the API reason when a submission is rejected", async () => {
        vi.mocked(createSubmission).mockRejectedValueOnce(
            new ApiRequestError(
                "The submission limit has been reached.",
                409,
                "submission_limit_reached",
            ),
        );
        renderProblemPage();

        fireEvent.click(
            await screen.findByRole("button", { name: "Submit for grading" }),
        );

        expect(
            await screen.findByText("The submission limit has been reached."),
        ).toBeTruthy();
    });

    it("lets keyboard users resize the solution pane", async () => {
        renderProblemPage();
        const divider = await screen.findByRole("separator", {
            name: "Resize problem and solution panels",
        });

        expect(divider.getAttribute("aria-valuenow")).toBe("32");
        fireEvent.keyDown(divider, { key: "ArrowLeft" });
        expect(divider.getAttribute("aria-valuenow")).toBe("30");
        fireEvent.keyDown(divider, { key: "Home" });
        expect(divider.getAttribute("aria-valuenow")).toBe("28");
    });
});
