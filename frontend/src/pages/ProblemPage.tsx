import Editor from "@monaco-editor/react";
import {
    useEffect,
    useRef,
    useState,
    type ComponentProps,
    type CSSProperties,
    type KeyboardEvent,
    type PointerEvent,
} from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import {
    getProblem,
    runPublicCases,
    startProblem,
    type ProblemDetail,
} from "../api/problems";
import {
    createSubmission,
    getSubmission,
    getSubmissionComplexity,
    type ComplexityAnalysis,
    type Submission,
} from "../api/submissions";
import ErrorState from "../components/ErrorState";
import LoadingState from "../components/LoadingState";
import { ApiRequestError } from "../api/client";
import { useTheme } from "../theme";

const POLL_INTERVAL_MS = 2000;
const MIN_PROMPT_WIDTH = 28;
const MAX_PROMPT_WIDTH = 62;

function defineEditorThemes(
    monaco: Parameters<NonNullable<ComponentProps<typeof Editor>["beforeMount"]>>[0],
) {
    monaco.editor.defineTheme("techniview-light", {
        base: "vs",
        inherit: true,
        rules: [{ token: "keyword", foreground: "006EAF" }],
        colors: {
            "editor.background": "#F8FBFC",
            "editor.foreground": "#101820",
            "editorLineNumber.foreground": "#667783",
            "editorCursor.foreground": "#006EAF",
            "editor.selectionBackground": "#CDE8F7",
            "editor.lineHighlightBackground": "#F5F8FA",
        },
    });
    monaco.editor.defineTheme("techniview-dark", {
        base: "vs-dark",
        inherit: true,
        rules: [{ token: "keyword", foreground: "80CFFF" }],
        colors: {
            "editor.background": "#14232E",
            "editor.foreground": "#EDF5F9",
            "editorLineNumber.foreground": "#A9BDCA",
            "editorCursor.foreground": "#80CFFF",
            "editor.selectionBackground": "#344B5B",
            "editor.lineHighlightBackground": "#253746",
        },
    });
}

function formatDueDate(value: string) {
    const timestamp = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`;
    return new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
    }).format(new Date(timestamp));
}

function newRequestKey(): string {
    if (typeof crypto.randomUUID === "function") {
        return crypto.randomUUID();
    }
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x40;
    bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80;
    const hex = [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function formatDifficulty(difficulty: ProblemDetail["difficulty"]) {
    return difficulty.charAt(0).toUpperCase() + difficulty.slice(1);
}

function initialAssignmentItemId(
    problem: ProblemDetail,
    search: string,
): number | null {
    const requested = new URLSearchParams(search).get("assignment_item_id");
    if (requested !== null) {
        const context = problem.assignment_contexts.find(
            (item) => item.assignment_item_id === Number(requested),
        );
        if (!context) {
            throw new Error("Assignment context is unavailable.");
        }
        return context.assignment_item_id;
    }
    return problem.origin === "custom"
        ? (problem.assignment_contexts[0]?.assignment_item_id ?? null)
        : null;
}

function submissionMessage(submission: Submission): string {
    if (submission.failure_message) {
        return submission.failure_message;
    }
    if (!submission.done) {
        const messages = {
            waiting_to_send: "Waiting for TechniView to send your code...",
            sending_to_go_judge: "Sending your code to go-judge...",
            waiting_on_go_judge: "Queued for go-judge...",
            running_on_go_judge: "Running in go-judge...",
            complete: "Finishing your result...",
        };
        return messages[submission.phase];
    }
    if (submission.is_practice_run) {
        return `${submission.passed_count}/${submission.test_count} public cases passed. This run did not use a graded attempt.`;
    }
    if (submission.status === "passed") {
        return `Accepted — ${submission.passed_count}/${submission.test_count} tests passed.`;
    }
    return `${submission.status.replace(/_/g, " ")} — ${submission.passed_count}/${submission.test_count} tests passed.`;
}

export default function ProblemPage() {
    const theme = useTheme();
    const { problemId } = useParams();
    const location = useLocation();
    const parsedProblemId = Number(problemId);
    const [problem, setProblem] = useState<ProblemDetail | null>(null);
    const [sourceCode, setSourceCode] = useState("");
    const [submission, setSubmission] = useState<Submission | null>(null);
    const [complexity, setComplexity] = useState<ComplexityAnalysis | null>(null);
    const [assignmentItemId, setAssignmentItemId] = useState<number | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isRunning, setIsRunning] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const pendingAction = useRef<{ signature: string; key: string } | null>(null);
    const workspaceRef = useRef<HTMLDivElement>(null);
    const draggingPointer = useRef<number | null>(null);
    const [promptWidth, setPromptWidth] = useState(32);

    function resizeFromPointer(clientX: number) {
        const bounds = workspaceRef.current?.getBoundingClientRect();
        if (!bounds || bounds.width === 0) return;
        const percentage = ((clientX - bounds.left) / bounds.width) * 100;
        setPromptWidth(
            Math.round(
                Math.min(MAX_PROMPT_WIDTH, Math.max(MIN_PROMPT_WIDTH, percentage)),
            ),
        );
    }

    function handleDividerKeyDown(event: KeyboardEvent<HTMLDivElement>) {
        const change =
            event.key === "ArrowLeft" ? -2 : event.key === "ArrowRight" ? 2 : 0;
        if (change) {
            event.preventDefault();
            setPromptWidth((width) =>
                Math.min(MAX_PROMPT_WIDTH, Math.max(MIN_PROMPT_WIDTH, width + change)),
            );
        } else if (event.key === "Home" || event.key === "End") {
            event.preventDefault();
            setPromptWidth(event.key === "Home" ? MIN_PROMPT_WIDTH : MAX_PROMPT_WIDTH);
        }
    }

    function handleDividerPointerDown(event: PointerEvent<HTMLDivElement>) {
        if (event.button !== 0) return;
        draggingPointer.current = event.pointerId;
        event.currentTarget.setPointerCapture(event.pointerId);
        resizeFromPointer(event.clientX);
    }

    function handleDividerPointerMove(event: PointerEvent<HTMLDivElement>) {
        if (draggingPointer.current === event.pointerId)
            resizeFromPointer(event.clientX);
    }

    function stopDividerDrag(event: PointerEvent<HTMLDivElement>) {
        if (draggingPointer.current !== event.pointerId) return;
        draggingPointer.current = null;
        if (event.currentTarget.hasPointerCapture(event.pointerId)) {
            event.currentTarget.releasePointerCapture(event.pointerId);
        }
    }

    function requestKey(operation: string, payload: Record<string, unknown>) {
        const signature = JSON.stringify({ operation, payload });
        if (pendingAction.current?.signature === signature) {
            return pendingAction.current;
        }
        const action = { signature, key: newRequestKey() };
        pendingAction.current = action;
        return action;
    }

    function completeRequest(action: { signature: string; key: string }) {
        if (pendingAction.current?.signature === action.signature) {
            pendingAction.current = null;
        }
    }

    useEffect(() => {
        if (!Number.isInteger(parsedProblemId) || parsedProblemId <= 0) {
            setError("This problem link is invalid.");
            setIsLoading(false);
            return;
        }

        let isCurrent = true;
        getProblem(parsedProblemId)
            .then(async (loadedProblem) => {
                const selected = initialAssignmentItemId(
                    loadedProblem,
                    location.search,
                );
                await startProblem(parsedProblemId, selected ?? undefined);
                if (!isCurrent) {
                    return;
                }
                setProblem(loadedProblem);
                setSourceCode(loadedProblem.starter_code);
                setAssignmentItemId(selected);
            })
            .catch(() => {
                if (isCurrent) {
                    setError("We could not load this problem.");
                }
            })
            .finally(() => {
                if (isCurrent) {
                    setIsLoading(false);
                }
            });

        return () => {
            isCurrent = false;
        };
    }, [location.search, parsedProblemId]);

    useEffect(() => {
        if (!submission || submission.done) {
            return;
        }

        let isCurrent = true;
        const poll = window.setInterval(() => {
            void getSubmission(submission.id)
                .then((updatedSubmission) => {
                    if (isCurrent) {
                        setSubmission(updatedSubmission);
                        if (updatedSubmission.done) {
                            setIsRunning(false);
                        }
                    }
                })
                .catch(() => {
                    if (isCurrent) {
                        setIsRunning(false);
                        setError("We could not retrieve the execution result.");
                    }
                });
        }, POLL_INTERVAL_MS);

        return () => {
            isCurrent = false;
            window.clearInterval(poll);
        };
    }, [submission]);

    useEffect(() => {
        if (!submission?.done || submission.is_practice_run) {
            return;
        }

        let isCurrent = true;
        let timeout: number | undefined;
        const pollComplexity = async () => {
            try {
                const result = await getSubmissionComplexity(submission.id);
                if (!isCurrent) {
                    return;
                }
                setComplexity(result);
                if (result.status === "queued" || result.status === "processing") {
                    timeout = window.setTimeout(pollComplexity, POLL_INTERVAL_MS);
                }
            } catch {
                if (isCurrent) {
                    setComplexity({
                        status: "unavailable",
                        time_complexity: null,
                        space_complexity: null,
                        model: "",
                        prompt_version: "",
                        error_code: "request_failed",
                        analyzed_at: null,
                    });
                }
            }
        };

        void pollComplexity();
        return () => {
            isCurrent = false;
            if (timeout !== undefined) {
                window.clearTimeout(timeout);
            }
        };
    }, [submission]);

    async function handleRun() {
        if (!problem || !sourceCode.trim() || isRunning) {
            return;
        }

        setError(null);
        setSubmission(null);
        setComplexity(null);
        setIsRunning(true);
        const action = requestKey("public_run", {
            problem_id: problem.id,
            source_code: sourceCode,
        });
        try {
            const createdRun = await runPublicCases(problem.id, sourceCode, action.key);
            setSubmission(createdRun);
            completeRequest(action);
            if (createdRun.done) {
                setIsRunning(false);
            }
        } catch (error) {
            setError(
                error instanceof ApiRequestError
                    ? error.message
                    : "We could not run the public cases. Please try again.",
            );
            setIsRunning(false);
        }
    }

    async function handleSubmit() {
        if (!problem || !sourceCode.trim() || isRunning) {
            return;
        }
        setError(null);
        setSubmission(null);
        setComplexity(null);
        setIsRunning(true);
        const payload = {
            problem_id: problem.id,
            assignment_item_id: assignmentItemId,
            source_code: sourceCode,
        };
        const action = requestKey("graded_submission", payload);
        try {
            const createdSubmission = await createSubmission(
                problem.id,
                sourceCode,
                action.key,
                assignmentItemId ?? undefined,
            );
            completeRequest(action);
            setSubmission(createdSubmission);
            if (createdSubmission.done) {
                setIsRunning(false);
            }
        } catch (error) {
            setIsRunning(false);
            setError(
                error instanceof ApiRequestError
                    ? error.message
                    : "We could not submit your code. Please try again.",
            );
        }
    }

    if (isLoading) {
        return <LoadingState message="Loading problem..." />;
    }
    if (error && !problem) {
        return <ErrorState message={error} />;
    }
    if (!problem) {
        return <ErrorState message="Problem not found." />;
    }

    const backPath = location.pathname.startsWith("/teacher/")
        ? "/teacher/problems"
        : "/student/problems";
    const selectedContext = problem.assignment_contexts.find(
        (item) => item.assignment_item_id === assignmentItemId,
    );

    return (
        <div className="problem-page">
            <p>
                <Link to={backPath}>
                    {backPath === "/teacher/problems"
                        ? "← Back to problems"
                        : "← Back to all problems"}
                </Link>
            </p>
            <header className="page-header">
                <h1>{problem.title}</h1>
                <p>
                    <strong>{formatDifficulty(problem.difficulty)}</strong>
                    {" · "}
                    {problem.test_count} test cases
                </p>
            </header>

            {problem.assignment_contexts.length > 0 && (
                <div className="problem-context-select">
                    <label>
                        Work for
                        <select
                            disabled={isRunning}
                            value={assignmentItemId ?? ""}
                            onChange={(event) => {
                                const selected = event.target.value
                                    ? Number(event.target.value)
                                    : null;
                                setAssignmentItemId(selected);
                                setSubmission(null);
                                setError(null);
                                void startProblem(
                                    problem.id,
                                    selected ?? undefined,
                                ).catch(() =>
                                    setError("We could not start this assignment."),
                                );
                            }}
                        >
                            {problem.origin !== "custom" && (
                                <option value="">Independent practice</option>
                            )}
                            {problem.assignment_contexts.map((context) => (
                                <option
                                    key={context.assignment_item_id}
                                    value={context.assignment_item_id}
                                >
                                    {context.course_name}: {context.assignment_title}
                                </option>
                            ))}
                        </select>
                    </label>
                </div>
            )}

            {error && <ErrorState message={error} />}

            <div
                className="problem-workspace"
                ref={workspaceRef}
                style={{ "--prompt-width": `${promptWidth}%` } as CSSProperties}
            >
                <section
                    aria-labelledby="prompt-heading"
                    className="problem-description"
                    id="problem-description-panel"
                >
                    <h2 id="prompt-heading">Problem</h2>
                    <div style={{ whiteSpace: "pre-wrap" }}>{problem.prompt}</div>
                    {problem.public_tests.length > 0 && (
                        <div>
                            <h3>Examples</h3>
                            {problem.public_tests.map((testCase) => (
                                <div key={testCase.id}>
                                    <p>
                                        <strong>Input:</strong> {testCase.input}
                                    </p>
                                    <p>
                                        <strong>Expected output:</strong>{" "}
                                        {testCase.expected_output}
                                    </p>
                                </div>
                            ))}
                        </div>
                    )}
                </section>

                <div
                    aria-controls="problem-description-panel problem-solution-panel"
                    aria-label="Resize problem and solution panels"
                    aria-orientation="vertical"
                    aria-valuemax={MAX_PROMPT_WIDTH}
                    aria-valuemin={MIN_PROMPT_WIDTH}
                    aria-valuenow={promptWidth}
                    className="problem-divider"
                    onKeyDown={handleDividerKeyDown}
                    onPointerCancel={stopDividerDrag}
                    onPointerDown={handleDividerPointerDown}
                    onPointerMove={handleDividerPointerMove}
                    onPointerUp={stopDividerDrag}
                    role="separator"
                    tabIndex={0}
                >
                    <span aria-hidden="true" />
                </div>

                <section
                    aria-labelledby="editor-heading"
                    className="problem-editor"
                    id="problem-solution-panel"
                >
                    <div>
                        <h2 id="editor-heading">Your solution</h2>
                        <p>Write Python 3 code, then run it against all test cases.</p>
                    </div>
                    <div className="submission-context">
                        {selectedContext ? (
                            <>
                                <strong>
                                    Assignment #{selectedContext.assignment_id}:{" "}
                                    {selectedContext.assignment_title}
                                </strong>
                                <span>
                                    {selectedContext.course_name} · Question{" "}
                                    {selectedContext.item_order}
                                </span>
                                <span>
                                    {selectedContext.due_at
                                        ? `Due ${formatDueDate(selectedContext.due_at)} (your time)`
                                        : "No due date"}
                                </span>
                            </>
                        ) : (
                            <>
                                <strong>Independent practice</strong>
                                <span>No assignment or due date</span>
                            </>
                        )}
                    </div>
                    <div className="code-editor-frame">
                        <Editor
                            beforeMount={defineEditorThemes}
                            defaultLanguage="python"
                            height="min(60vh, 560px)"
                            onChange={(value: string | undefined) =>
                                setSourceCode(value ?? "")
                            }
                            options={{
                                minimap: { enabled: false },
                                fontSize: 14,
                                automaticLayout: true,
                                scrollBeyondLastLine: false,
                                scrollbar: {
                                    vertical: "hidden",
                                    horizontal: "hidden",
                                    verticalScrollbarSize: 0,
                                    horizontalScrollbarSize: 0,
                                    useShadows: false,
                                },
                                overviewRulerLanes: 0,
                                overviewRulerBorder: false,
                            }}
                            theme={
                                theme === "dark"
                                    ? "techniview-dark"
                                    : "techniview-light"
                            }
                            value={sourceCode}
                        />
                    </div>
                    <button
                        disabled={isRunning || !sourceCode.trim()}
                        onClick={() => void handleRun()}
                        type="button"
                    >
                        {isRunning ? "Working..." : "Run public cases"}
                    </button>
                    <button
                        disabled={isRunning || !sourceCode.trim()}
                        onClick={() => void handleSubmit()}
                        type="button"
                    >
                        Submit for grading
                    </button>
                    {submission && (
                        <section
                            aria-live="polite"
                            aria-labelledby="result-heading"
                            className="submission-results"
                        >
                            <h3 id="result-heading">
                                {submission.is_practice_run
                                    ? "Public case results"
                                    : "Submission result"}
                            </h3>
                            <p>{submissionMessage(submission)}</p>
                            {!submission.is_practice_run && submission.done && (
                                <section aria-labelledby="complexity-heading">
                                    <h4 id="complexity-heading">
                                        Estimated complexity
                                    </h4>
                                    {complexity === null ||
                                    complexity.status === "queued" ||
                                    complexity.status === "processing" ? (
                                        <p>Analyzing your solution...</p>
                                    ) : complexity.status === "complete" ? (
                                        <dl>
                                            <div>
                                                <dt>Time</dt>
                                                <dd>{complexity.time_complexity}</dd>
                                            </div>
                                            <div>
                                                <dt>Auxiliary space</dt>
                                                <dd>{complexity.space_complexity}</dd>
                                            </div>
                                        </dl>
                                    ) : complexity.status === "disabled" ? (
                                        <p>
                                            AI complexity estimates are not enabled for
                                            this deployment.
                                        </p>
                                    ) : complexity.status === "failed" ? (
                                        <p>
                                            The complexity estimate failed. Your grading
                                            result is unaffected.
                                        </p>
                                    ) : complexity.error_code === "request_failed" ? (
                                        <p>
                                            Could not load the complexity estimate. Try
                                            refreshing the page.
                                        </p>
                                    ) : (
                                        <p>
                                            No complexity estimate was recorded for this
                                            submission.
                                        </p>
                                    )}
                                    <p>
                                        This is an AI estimate of growth, not a runtime
                                        measurement. It does not affect grading.
                                    </p>
                                </section>
                            )}
                            {submission.public_results.length > 0 && (
                                <>
                                    {!submission.is_practice_run && (
                                        <p>
                                            Showing details for{" "}
                                            {submission.public_results.length} public
                                            {submission.public_results.length === 1
                                                ? " test"
                                                : " tests"}
                                            .
                                            {submission.test_count >
                                                submission.public_results.length &&
                                                " Private tests count toward the result above, but their details are hidden."}
                                        </p>
                                    )}
                                    <ul>
                                        {submission.public_results.map((result) => (
                                            <li key={result.case_order}>
                                                Test {result.case_order}:{" "}
                                                {result.friendly_message}
                                                {result.stdout && (
                                                    <pre>{result.stdout}</pre>
                                                )}
                                                {result.stderr && (
                                                    <pre>{result.stderr}</pre>
                                                )}
                                                {result.compile_output && (
                                                    <pre>{result.compile_output}</pre>
                                                )}
                                            </li>
                                        ))}
                                    </ul>
                                </>
                            )}
                        </section>
                    )}
                </section>
            </div>
        </div>
    );
}
