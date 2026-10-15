import Editor from "@monaco-editor/react";
import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { getProblem, startProblem, type ProblemDetail } from "../api/problems";
import { createSubmission, getSubmission, type Submission } from "../api/submissions";
import ErrorState from "../components/ErrorState";
import LoadingState from "../components/LoadingState";

const POLL_INTERVAL_MS = 1000;

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
    if (!submission.done) {
        return submission.status === "running"
            ? "Running your code..."
            : "Queued for execution...";
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
    const [assignmentItemId, setAssignmentItemId] = useState<number | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isRunning, setIsRunning] = useState(false);
    const [error, setError] = useState<string | null>(null);

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

    async function handleRun() {
        if (!problem || !sourceCode.trim() || isRunning) {
            return;
        }

        setError(null);
        setSubmission(null);
        setIsRunning(true);
        try {
            const createdSubmission = await createSubmission(
                problem.id,
                sourceCode,
                assignmentItemId ?? undefined,
            );
            setSubmission(createdSubmission);
            if (createdSubmission.done) {
                setIsRunning(false);
            }
        } catch {
            setIsRunning(false);
            setError("We could not run your code. Please try again.");
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
                        {isRunning ? "Running..." : "Run code"}
                    </button>
                    {submission && (
                        <section aria-live="polite" aria-labelledby="result-heading">
                            <h3 id="result-heading">Execution result</h3>
                            <p>{submissionMessage(submission)}</p>
                            {submission.done &&
                                submission.public_results.length > 0 && (
                                    <ul>
                                        {submission.public_results.map((result) => (
                                            <li key={result.case_order}>
                                                Test {result.case_order}:{" "}
                                                {result.friendly_message}
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
