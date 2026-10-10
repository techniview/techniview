import { useEffect, useState } from "react";
import {
    getClassAnalytics,
    getClassMembers,
    getStudentProblemAnalytics,
    getTeacherCourses,
    type ClassMember,
    type Course,
} from "../../api/analytics";
import ErrorState from "../../components/ErrorState";
import LoadingState from "../../components/LoadingState";
import type { AnalyticsMetrics, ProblemAnalytics } from "../../types/analytics";

type StudentRow = {
    member: ClassMember;
    metrics: AnalyticsMetrics | null;
    error: boolean;
};

function formatTime(seconds: number | null): string {
    if (seconds === null) {
        return "Not completed";
    }
    if (seconds < 60) {
        return `${Math.round(seconds)} sec`;
    }
    return `${(seconds / 60).toFixed(1)} min`;
}

function statusFor(metrics: AnalyticsMetrics | null): string {
    if (metrics === null || metrics.started_count === 0) {
        return "Not started";
    }
    if (metrics.completed_count === 0) {
        return "In progress";
    }
    return "Completed";
}

function emptyStudentRow(member: ClassMember): StudentRow {
    return { member, metrics: null, error: false };
}

export default function TeacherClassPage() {
    const [course, setCourse] = useState<Course | null>(null);
    const [members, setMembers] = useState<ClassMember[]>([]);
    const [problems, setProblems] = useState<ProblemAnalytics[]>([]);
    const [selectedProblemId, setSelectedProblemId] = useState("");
    const [studentRows, setStudentRows] = useState<StudentRow[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isLoadingDetails, setIsLoadingDetails] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let isCurrent = true;

        async function loadClass() {
            try {
                const courses = await getTeacherCourses();
                const teacherCourse = courses.items[0];
                if (!teacherCourse) {
                    throw new Error("No course found.");
                }

                const [memberResponse, analytics] = await Promise.all([
                    getClassMembers(teacherCourse.id),
                    getClassAnalytics(teacherCourse.id),
                ]);
                if (!isCurrent) {
                    return;
                }

                setCourse(teacherCourse);
                setMembers(
                    memberResponse.items.filter((member) => member.role === "student"),
                );
                setProblems(analytics.items);
                if (analytics.items[0]) {
                    setSelectedProblemId(String(analytics.items[0].problem.id));
                }
            } catch {
                if (isCurrent) {
                    setError("We could not load the class overview.");
                }
            } finally {
                if (isCurrent) {
                    setIsLoading(false);
                }
            }
        }

        void loadClass();
        return () => {
            isCurrent = false;
        };
    }, []);

    useEffect(() => {
        if (!course || !selectedProblemId) {
            setStudentRows([]);
            return;
        }

        let isCurrent = true;
        setIsLoadingDetails(true);
        const problemId = Number(selectedProblemId);

        Promise.all(
            members.map(async (member) => {
                try {
                    const result = await getStudentProblemAnalytics(
                        course.id,
                        member.user_id,
                        problemId,
                    );
                    return { member, metrics: result.metrics, error: false };
                } catch {
                    return { ...emptyStudentRow(member), error: true };
                }
            }),
        )
            .then((rows) => {
                if (isCurrent) {
                    setStudentRows(rows);
                }
            })
            .finally(() => {
                if (isCurrent) {
                    setIsLoadingDetails(false);
                }
            });

        return () => {
            isCurrent = false;
        };
    }, [course, members, selectedProblemId]);

    if (isLoading) {
        return <LoadingState message="Loading class overview..." />;
    }
    if (error) {
        return <ErrorState message={error} />;
    }

    const selectedProblem = problems.find(
        (item) => String(item.problem.id) === selectedProblemId,
    );

    return (
        <div className="teacher-class-page">
            <header className="page-header">
                <p className="eyebrow">Teacher dashboard</p>
                <h1>{course?.name ?? "Class Overview"}</h1>
                <p>Review student progress for each assigned problem.</p>
            </header>

            <section aria-labelledby="problem-heading" className="filter-panel">
                <div>
                    <h2 id="problem-heading">Problem performance</h2>
                    <p>Select a problem to see each student&apos;s progress.</p>
                </div>
                <label>
                    Problem
                    <select
                        aria-label="Problem"
                        onChange={(event) => setSelectedProblemId(event.target.value)}
                        value={selectedProblemId}
                    >
                        {problems.length === 0 && (
                            <option value="">No problems assigned</option>
                        )}
                        {problems.map((item) => (
                            <option key={item.problem.id} value={item.problem.id}>
                                {item.problem.title}
                            </option>
                        ))}
                    </select>
                </label>
            </section>

            {selectedProblem && (
                <p>
                    {selectedProblem.problem.difficulty} ·{" "}
                    {selectedProblem.metrics.completed_count} of{" "}
                    {selectedProblem.metrics.assigned_count} completed
                </p>
            )}

            {isLoadingDetails ? (
                <LoadingState message="Loading student progress..." />
            ) : (
                <div className="table-wrapper">
                    <table>
                        <caption className="visually-hidden">
                            Student progress for the selected problem
                        </caption>
                        <thead>
                            <tr>
                                <th scope="col">Student</th>
                                <th scope="col">Status</th>
                                <th scope="col">Time to complete</th>
                                <th scope="col">Retries</th>
                            </tr>
                        </thead>
                        <tbody>
                            {studentRows.map(({ member, metrics, error: rowError }) => (
                                <tr key={member.user_id}>
                                    <th scope="row">{member.name}</th>
                                    <td>
                                        {rowError ? "Unavailable" : statusFor(metrics)}
                                    </td>
                                    <td>
                                        {rowError
                                            ? "Unavailable"
                                            : formatTime(
                                                  metrics?.avg_completion_seconds ??
                                                      null,
                                              )}
                                    </td>
                                    <td>
                                        {rowError
                                            ? "Unavailable"
                                            : (metrics?.total_retries ?? 0)}
                                    </td>
                                </tr>
                            ))}
                            {studentRows.length === 0 && (
                                <tr>
                                    <td colSpan={4}>No students found.</td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
