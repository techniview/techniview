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

type ProblemRow = {
    problem: ProblemAnalytics["problem"];
    metrics: AnalyticsMetrics | null;
    unavailable: boolean;
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

export default function TeacherProblemPage() {
    const [course, setCourse] = useState<Course | null>(null);
    const [students, setStudents] = useState<ClassMember[]>([]);
    const [problems, setProblems] = useState<ProblemAnalytics[]>([]);
    const [selectedStudentId, setSelectedStudentId] = useState("");
    const [rows, setRows] = useState<ProblemRow[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isLoadingProgress, setIsLoadingProgress] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let isCurrent = true;

        async function loadPage() {
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

                const classStudents = memberResponse.items.filter(
                    (member) => member.role === "student",
                );
                setCourse(teacherCourse);
                setStudents(classStudents);
                setProblems(analytics.items);
                if (classStudents[0]) {
                    setSelectedStudentId(String(classStudents[0].user_id));
                }
            } catch {
                if (isCurrent) {
                    setError("We could not load the class problem progress.");
                }
            } finally {
                if (isCurrent) {
                    setIsLoading(false);
                }
            }
        }

        void loadPage();
        return () => {
            isCurrent = false;
        };
    }, []);

    useEffect(() => {
        if (!course || !selectedStudentId) {
            setRows([]);
            return;
        }

        let isCurrent = true;
        setIsLoadingProgress(true);
        const studentId = Number(selectedStudentId);

        Promise.all(
            problems.map(async ({ problem }) => {
                try {
                    const result = await getStudentProblemAnalytics(
                        course.id,
                        studentId,
                        problem.id,
                    );
                    return {
                        problem,
                        metrics: result.metrics,
                        unavailable: false,
                    };
                } catch {
                    return {
                        problem,
                        metrics: null,
                        unavailable: true,
                    };
                }
            }),
        )
            .then((problemRows) => {
                if (isCurrent) {
                    setRows(problemRows);
                }
            })
            .finally(() => {
                if (isCurrent) {
                    setIsLoadingProgress(false);
                }
            });

        return () => {
            isCurrent = false;
        };
    }, [course, problems, selectedStudentId]);

    if (isLoading) {
        return <LoadingState message="Loading problem progress..." />;
    }
    if (error) {
        return <ErrorState message={error} />;
    }

    const selectedStudent = students.find(
        (student) => String(student.user_id) === selectedStudentId,
    );

    return (
        <div className="teacher-problem-page">
            <header className="page-header">
                <p className="eyebrow">Teacher dashboard</p>
                <h1>Student Problem Progress</h1>
                <p>
                    Review one student&apos;s progress across every problem in{" "}
                    {course?.name ?? "the class"}.
                </p>
            </header>

            <section aria-labelledby="student-heading" className="filter-panel">
                <div>
                    <h2 id="student-heading">Select a student</h2>
                    <p>Choose a student to view their problem history.</p>
                </div>
                <label>
                    Student
                    <select
                        aria-label="Student"
                        onChange={(event) => setSelectedStudentId(event.target.value)}
                        value={selectedStudentId}
                    >
                        {students.length === 0 && (
                            <option value="">No students found</option>
                        )}
                        {students.map((student) => (
                            <option key={student.user_id} value={student.user_id}>
                                {student.name}
                            </option>
                        ))}
                    </select>
                </label>
            </section>

            {selectedStudent && (
                <p>
                    Showing progress for <strong>{selectedStudent.name}</strong>
                </p>
            )}

            {isLoadingProgress ? (
                <LoadingState message="Loading student problem progress..." />
            ) : (
                <div className="table-wrapper">
                    <table>
                        <caption className="visually-hidden">
                            Problem progress for the selected student
                        </caption>
                        <thead>
                            <tr>
                                <th scope="col">Problem</th>
                                <th scope="col">Difficulty</th>
                                <th scope="col">Status</th>
                                <th scope="col">Time to complete</th>
                                <th scope="col">Retries</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map(({ problem, metrics, unavailable }) => (
                                <tr key={problem.id}>
                                    <th scope="row">{problem.title}</th>
                                    <td>{problem.difficulty}</td>
                                    <td>
                                        {unavailable
                                            ? "Unavailable"
                                            : statusFor(metrics)}
                                    </td>
                                    <td>
                                        {unavailable
                                            ? "Unavailable"
                                            : formatTime(
                                                  metrics?.avg_completion_seconds ??
                                                      null,
                                              )}
                                    </td>
                                    <td>
                                        {unavailable
                                            ? "Unavailable"
                                            : (metrics?.total_retries ?? 0)}
                                    </td>
                                </tr>
                            ))}
                            {rows.length === 0 && (
                                <tr>
                                    <td colSpan={5}>No problems found.</td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
