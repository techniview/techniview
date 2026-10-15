import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { Assignment, Course } from "../../api/analytics";
import { listAssignments } from "../../api/assignments";
import { getCourse } from "../../api/courses";
import ErrorState from "../../components/ErrorState";
import LoadingState from "../../components/LoadingState";

async function availableAssignments(courseId: number): Promise<Assignment[]> {
    const assignments: Assignment[] = [];
    let offset = 0;
    while (true) {
        const page = await listAssignments(courseId, 100, offset);
        assignments.push(...page.items.filter((item) => item.state === "published"));
        offset += page.items.length;
        if (page.items.length === 0 || offset >= page.total) {
            return assignments;
        }
    }
}

export default function StudentCoursePage() {
    const { courseId } = useParams();
    const [course, setCourse] = useState<Course | null>(null);
    const [assignments, setAssignments] = useState<Assignment[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const id = Number(courseId);
        if (!Number.isSafeInteger(id) || id <= 0) {
            setError("This class link is invalid.");
            setIsLoading(false);
            return;
        }

        let isCurrent = true;
        async function loadCourse() {
            try {
                const result = await getCourse(id);
                if (result.membership_role !== "student") {
                    throw new Error("This class is unavailable.");
                }
                const items =
                    result.withdrawn_at === null && result.archived_at === null
                        ? await availableAssignments(id)
                        : [];
                if (isCurrent) {
                    setCourse(result);
                    setAssignments(items);
                }
            } catch {
                if (isCurrent) {
                    setError("We could not load this class.");
                }
            } finally {
                if (isCurrent) {
                    setIsLoading(false);
                }
            }
        }

        void loadCourse();
        return () => {
            isCurrent = false;
        };
    }, [courseId]);

    if (isLoading) {
        return <LoadingState message="Loading class..." />;
    }
    if (error || !course) {
        return <ErrorState message={error ?? "This class is unavailable."} />;
    }

    const inactive = course.withdrawn_at !== null || course.archived_at !== null;

    return (
        <div className="student-course-page">
            <header className="page-header">
                <p className="eyebrow">Your class</p>
                <h1>{course.name}</h1>
                {course.description && <p>{course.description}</p>}
            </header>

            {inactive ? (
                <p>This class is no longer available for new work.</p>
            ) : (
                <section aria-labelledby="assignments-heading">
                    <h2 id="assignments-heading">Assignments</h2>
                    {assignments.length === 0 ? (
                        <p>No assignments are available yet.</p>
                    ) : (
                        assignments.map((assignment) => (
                            <section key={assignment.id}>
                                <h3>{assignment.title}</h3>
                                {assignment.description && (
                                    <p>{assignment.description}</p>
                                )}
                                <ul>
                                    {assignment.items.map((item) => (
                                        <li key={item.id}>
                                            <Link
                                                to={`/student/problems/${item.problem.id}?assignment_item_id=${item.id}`}
                                            >
                                                {item.problem.title}
                                            </Link>
                                        </li>
                                    ))}
                                </ul>
                            </section>
                        ))
                    )}
                </section>
            )}

            <p>
                <Link to="/student/problems">Browse available problems</Link>
            </p>
        </div>
    );
}
