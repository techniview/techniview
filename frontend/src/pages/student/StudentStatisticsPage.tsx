import { useEffect, useState } from "react";
import {
    getProblemTypes,
    getStudentAnalytics,
    type CurriculumPool,
} from "../../api/analytics";
import ErrorState from "../../components/ErrorState";
import LoadingState from "../../components/LoadingState";
import PerformanceCharts from "../../components/PerformanceCharts";
import type { AnalyticsMetrics } from "../../types/analytics";

type Difficulty = "easy" | "medium" | "hard";

function formatMinutes(seconds: number | null): string {
    if (seconds === null) {
        return "No data";
    }

    if (seconds < 60) {
        return `${Math.round(seconds)} sec`;
    }

    return `${(seconds / 60).toFixed(1)} min`;
}

function formatAverage(value: number | null): string {
    return value === null ? "No data" : value.toFixed(1);
}

function StudentMetrics({ metrics }: { metrics: AnalyticsMetrics }) {
    const completion =
        metrics.completion_rate === null
            ? "--"
            : `${Math.round(metrics.completion_rate * 100)}%`;
    return (
        <dl className="statistics-summary" aria-label="Your performance">
            <div>
                <dt>Completed</dt>
                <dd>{metrics.completed_count}</dd>
                <span>of {metrics.assigned_count} assigned</span>
            </div>
            <div>
                <dt>Completion rate</dt>
                <dd>{completion}</dd>
                <span>across this view</span>
            </div>
            <div>
                <dt>Average time</dt>
                <dd>{formatMinutes(metrics.avg_completion_seconds)}</dd>
                <span>to complete a problem</span>
            </div>
            <div>
                <dt>Average retries</dt>
                <dd>{formatAverage(metrics.avg_retries_per_student)}</dd>
                <span>per problem</span>
            </div>
        </dl>
    );
}

export default function StudentStatisticsPage() {
    const [difficulty, setDifficulty] = useState<Difficulty | "">("");
    const [problemType, setProblemType] = useState("");
    const [problemTypes, setProblemTypes] = useState<CurriculumPool[]>([]);
    const [metrics, setMetrics] = useState<AnalyticsMetrics | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let isCurrent = true;

        getProblemTypes()
            .then((types) => {
                if (isCurrent) {
                    setProblemTypes(types);
                }
            })
            .catch(() => {
                if (isCurrent) {
                    setError("We could not load the problem type filter.");
                }
            });

        return () => {
            isCurrent = false;
        };
    }, []);

    useEffect(() => {
        let isCurrent = true;
        setIsLoading(true);
        setError(null);

        getStudentAnalytics(difficulty || null, problemType || null)
            .then((response) => {
                if (isCurrent) {
                    setMetrics(response.metrics);
                }
            })
            .catch(() => {
                if (isCurrent) {
                    setMetrics(null);
                    setError("We could not load your statistics.");
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
    }, [difficulty, problemType]);

    function clearFilters() {
        setDifficulty("");
        setProblemType("");
    }

    return (
        <div className="student-statistics-page">
            <header className="page-header">
                <h1>My Statistics</h1>
                <p>Track how you are progressing across your assigned problems.</p>
            </header>

            <section aria-label="Filter statistics" className="filter-panel">
                <div className="filter-controls">
                    <label>
                        Difficulty
                        <select
                            aria-label="Problem difficulty"
                            onChange={(event) =>
                                setDifficulty(event.target.value as Difficulty | "")
                            }
                            value={difficulty}
                        >
                            <option value="">All difficulties</option>
                            <option value="easy">Easy</option>
                            <option value="medium">Medium</option>
                            <option value="hard">Hard</option>
                        </select>
                    </label>
                    <label>
                        Problem type
                        <select
                            aria-label="Problem type"
                            onChange={(event) => setProblemType(event.target.value)}
                            value={problemType}
                        >
                            <option value="">All problem types</option>
                            {problemTypes.map((type) => (
                                <option key={type.slug} value={type.slug}>
                                    {type.name}
                                </option>
                            ))}
                        </select>
                    </label>
                    {(difficulty || problemType) && (
                        <button onClick={clearFilters} type="button">
                            Clear filters
                        </button>
                    )}
                </div>
            </section>

            {error && <ErrorState message={error} />}
            {isLoading && <LoadingState message="Loading your statistics..." />}
            {!isLoading && !error && metrics && (
                <>
                    <StudentMetrics metrics={metrics} />
                    <PerformanceCharts metrics={metrics} />
                </>
            )}
        </div>
    );
}
