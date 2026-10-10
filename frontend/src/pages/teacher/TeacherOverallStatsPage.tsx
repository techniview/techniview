import { useEffect, useState } from "react";
import {
    getClassAnalytics,
    getProblemTypes,
    getTeacherCourses,
    type Course,
    type CurriculumPool,
} from "../../api/analytics";
import ErrorState from "../../components/ErrorState";
import LoadingState from "../../components/LoadingState";
import StatCard from "../../components/StatCard";
import type { AnalyticsMetrics } from "../../types/analytics";

type Difficulty = "easy" | "medium" | "hard";

function formatTime(seconds: number | null): string {
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

function SummaryMetrics({ metrics }: { metrics: AnalyticsMetrics }) {
    return (
        <section aria-labelledby="summary-heading">
            <h2 id="summary-heading">Summary statistics</h2>
            <div className="stat-card-grid">
                <StatCard
                    label="Completion rate"
                    value={
                        metrics.completion_rate === null
                            ? "No data"
                            : `${Math.round(metrics.completion_rate * 100)}%`
                    }
                />
                <StatCard
                    label="Average time to complete"
                    value={formatTime(metrics.avg_completion_seconds)}
                />
                <StatCard
                    label="Average retries used"
                    value={formatAverage(metrics.avg_retries_per_student)}
                />
                <StatCard
                    label="Problems assigned"
                    value={String(metrics.assigned_count)}
                />
                <StatCard
                    label="Problems completed"
                    value={String(metrics.completed_count)}
                />
            </div>
        </section>
    );
}

export default function TeacherOverallStatsPage() {
    const [course, setCourse] = useState<Course | null>(null);
    const [problemTypes, setProblemTypes] = useState<CurriculumPool[]>([]);
    const [difficulty, setDifficulty] = useState<Difficulty | "">("");
    const [problemType, setProblemType] = useState("");
    const [metrics, setMetrics] = useState<AnalyticsMetrics | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let isCurrent = true;

        Promise.all([getTeacherCourses(), getProblemTypes()])
            .then(([courses, types]) => {
                if (!isCurrent) {
                    return;
                }
                const teacherCourse = courses.items[0];
                if (!teacherCourse) {
                    throw new Error("No course found.");
                }
                setCourse(teacherCourse);
                setProblemTypes(types);
            })
            .catch(() => {
                if (isCurrent) {
                    setError("We could not load the class filters.");
                    setIsLoading(false);
                }
            });

        return () => {
            isCurrent = false;
        };
    }, []);

    useEffect(() => {
        if (!course) {
            return;
        }

        let isCurrent = true;
        setIsLoading(true);
        setError(null);

        const params = new URLSearchParams();
        if (difficulty) {
            params.set("difficulty", difficulty);
        }
        if (problemType) {
            params.set("tag", problemType);
        }

        getClassAnalytics(course.id, params.toString() ? `?${params.toString()}` : "")
            .then((response) => {
                if (isCurrent) {
                    setMetrics(response.summary);
                }
            })
            .catch(() => {
                if (isCurrent) {
                    setMetrics(null);
                    setError("We could not load the summary statistics.");
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
    }, [course, difficulty, problemType]);

    function clearFilters() {
        setDifficulty("");
        setProblemType("");
    }

    return (
        <div className="teacher-overall-stats-page">
            <header className="page-header">
                <p className="eyebrow">Teacher dashboard</p>
                <h1>Overall Class Statistics</h1>
                <p>View class performance for {course?.name ?? "your course"}.</p>
            </header>

            <section aria-labelledby="filters-heading" className="filter-panel">
                <div>
                    <h2 id="filters-heading">Filter statistics</h2>
                    <p>Choose either filter or combine both.</p>
                </div>
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
            {isLoading && <LoadingState message="Loading class statistics..." />}
            {!isLoading && !error && metrics && <SummaryMetrics metrics={metrics} />}
        </div>
    );
}
