import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
    getStudentAssignments,
    getTeacherCourses,
    type Assignment,
    type Course,
} from "../../api/analytics";
import { getAvailableProblems, type ProblemSummary } from "../../api/problems";
import ErrorState from "../../components/ErrorState";
import LoadingState from "../../components/LoadingState";

function formatDifficulty(difficulty: ProblemSummary["difficulty"]): string {
    return difficulty.charAt(0).toUpperCase() + difficulty.slice(1);
}

async function courseAssignments(courseId: number): Promise<Assignment[]> {
    const assignments: Assignment[] = [];
    while (true) {
        const page = await getStudentAssignments(courseId, assignments.length);
        assignments.push(...page.items);
        if (assignments.length >= page.total || page.items.length === 0) {
            return assignments;
        }
    }
}

export default function StudentProblemsPage() {
    const [problems, setProblems] = useState<ProblemSummary[]>([]);
    const [assignmentItemsByProblem, setAssignmentItemsByProblem] = useState<
        Map<number, number>
    >(new Map());
    const [course, setCourse] = useState<Course | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let isCurrent = true;

        async function loadProblems() {
            try {
                const [problemResponse, courses] = await Promise.all([
                    getAvailableProblems(),
                    getTeacherCourses(),
                ]);
                const studentCourse = courses.items[0];
                const assignmentLists = await Promise.all(
                    courses.items.map((item) => courseAssignments(item.id)),
                );
                const assignedItems = new Map<number, number>();
                assignmentLists.forEach((list) =>
                    list.forEach((assignment) =>
                        assignment.items.forEach((item) => {
                            if (!assignedItems.has(item.problem.id)) {
                                assignedItems.set(item.problem.id, item.id);
                            }
                        }),
                    ),
                );

                if (isCurrent) {
                    setProblems(problemResponse.items);
                    setAssignmentItemsByProblem(assignedItems);
                    setCourse(studentCourse ?? null);
                }
            } catch {
                if (isCurrent) {
                    setError("We could not load the available problems.");
                }
            } finally {
                if (isCurrent) {
                    setIsLoading(false);
                }
            }
        }

        void loadProblems();
        return () => {
            isCurrent = false;
        };
    }, []);

    if (isLoading) {
        return <LoadingState message="Loading available problems..." />;
    }
    if (error) {
        return <ErrorState message={error} />;
    }

    return (
        <div className="student-problems-page">
            <header className="page-header">
                <p className="eyebrow">Student dashboard</p>
                <h1>Available Problems</h1>
                <p>
                    Practice problems available to you
                    {course ? ` in ${course.name}` : ""}.
                </p>
            </header>

            <div className="table-wrapper">
                <table>
                    <caption className="visually-hidden">
                        Available student problems
                    </caption>
                    <thead>
                        <tr>
                            <th scope="col">Problem</th>
                            <th scope="col">Difficulty</th>
                            <th scope="col">Type</th>
                            <th scope="col">Assignment</th>
                            <th scope="col">Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {problems.map((problem) => {
                            const problemType =
                                problem.typed_tags.find(
                                    (tag) => tag.kind === "problem_type",
                                )?.name ??
                                problem.tags[0] ??
                                "General";
                            const assignmentItemId = assignmentItemsByProblem.get(
                                problem.id,
                            );
                            const isAssigned = assignmentItemId !== undefined;

                            return (
                                <tr key={problem.id}>
                                    <th scope="row">{problem.title}</th>
                                    <td>{formatDifficulty(problem.difficulty)}</td>
                                    <td>{problemType}</td>
                                    <td>
                                        {isAssigned ? (
                                            <span aria-label="Assigned">Assigned</span>
                                        ) : (
                                            "Practice"
                                        )}
                                    </td>
                                    <td>
                                        <Link
                                            to={`/student/problems/${problem.id}${isAssigned ? `?assignment_item_id=${assignmentItemId}` : ""}`}
                                        >
                                            Open problem
                                        </Link>
                                    </td>
                                </tr>
                            );
                        })}
                        {problems.length === 0 && (
                            <tr>
                                <td colSpan={5}>No problems are available.</td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
