import Editor from "@monaco-editor/react";
import { useEffect, useRef, useState } from "react";
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

const POLL_INTERVAL_MS = 2000;

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
            sending_to_judge0: "Sending your code to Judge0...",
            waiting_on_judge0: "Queued in Judge0...",
            running_on_judge0: "Running in Judge0...",
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

    function requestKey(operation: string, payload: Record<string, unknown>) {
        const signature = JSON.stringify({ operation, payload });
        if (pendingAction.current?.signature === signature) {
            return pendingAction.current;
        }
        const action = { signature, key: crypto.randomUUID() };
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
            setSubmission(await runPublicCases(problem.id, sourceCode, action.key));
            completeRequest(action);
        } catch {
            setError("We could not run the public cases. Please try again.");
        } finally {
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
        } catch {
            setIsRunning(false);
            setError("We could not submit your code. Please try again.");
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
        : "/student/statistics";

    return (
        <div className="problem-page">
            <p>
                <Link to={backPath}>
                    {backPath === "/teacher/problems"
                        ? "← Back to problems"
                        : "← Back to statistics"}
                </Link>
            </p>
            <header className="page-header">
                <p className="eyebrow">Practice problem</p>
                <h1>{problem.title}</h1>
                <p>
                    <strong>{formatDifficulty(problem.difficulty)}</strong>
                    {" · "}
                    {problem.test_count} test cases
                </p>
            </header>

            {problem.assignment_contexts.length > 0 && (
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
                            void startProblem(problem.id, selected ?? undefined).catch(
                                () => setError("We could not start this assignment."),
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
            )}

            {error && <ErrorState message={error} />}

            <div className="problem-workspace">
                <section
                    aria-labelledby="prompt-heading"
                    className="problem-description"
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

                <section aria-labelledby="editor-heading" className="problem-editor">
                    <div>
                        <h2 id="editor-heading">Your solution</h2>
                        <p>Write Python 3 code, then run it against all test cases.</p>
                    </div>
                    <Editor
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
                        }}
                        theme="vs-dark"
                        value={sourceCode}
                    />
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
                        <section aria-live="polite" aria-labelledby="result-heading">
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
                                    ) : (
                                        <p>Complexity estimate unavailable.</p>
                                    )}
                                    <p>
                                        This is an AI estimate of growth, not a runtime
                                        measurement. It does not affect grading.
                                    </p>
                                </section>
                            )}
                            {submission.public_results.length > 0 && (
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
                            )}
                        </section>
                    )}
                </section>
            </div>
        </div>
    );
}
