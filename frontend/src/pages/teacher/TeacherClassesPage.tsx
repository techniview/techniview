import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { Course } from "../../api/analytics";
import { listCourses } from "../../api/courses";
import ErrorState from "../../components/ErrorState";
import LoadingState from "../../components/LoadingState";

async function staffCourses(): Promise<Course[]> {
    const courses: Course[] = [];
    let offset = 0;
    while (true) {
        const page = await listCourses(100, offset);
        courses.push(
            ...page.items.filter(
                (course) =>
                    course.membership_role !== "student" &&
                    course.withdrawn_at === null,
            ),
        );
        offset += page.items.length;
        if (page.items.length === 0 || offset >= page.total) {
            return courses;
        }
    }
}

export default function TeacherClassesPage() {
    const [courses, setCourses] = useState<Course[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let isCurrent = true;
        void staffCourses()
            .then((items) => {
                if (isCurrent) setCourses(items);
            })
            .catch(() => {
                if (isCurrent) setError("We could not load your classes.");
            })
            .finally(() => {
                if (isCurrent) setIsLoading(false);
            });
        return () => {
            isCurrent = false;
        };
    }, []);

    if (isLoading) return <LoadingState message="Loading your classes..." />;
    if (error) return <ErrorState message={error} />;

    return (
        <div className="teacher-classes-page">
            <header className="page-header">
                <h1>My Classes</h1>
                <p>Choose a class to review student progress.</p>
            </header>
            {courses.length === 0 ? (
                <p className="teacher-classes-empty">
                    You are not assigned to any classes yet.
                </p>
            ) : (
                <ul className="teacher-course-list">
                    {courses.map((course) => (
                        <li key={course.id}>
                            {course.archived_at === null ? (
                                <Link to={`/teacher/classes/${course.id}`}>
                                    <span>{course.name}</span>
                                    <span aria-hidden="true">→</span>
                                </Link>
                            ) : (
                                <div className="teacher-course-archived">
                                    <span>{course.name}</span>
                                    <span>Archived</span>
                                </div>
                            )}
                            {course.description && <p>{course.description}</p>}
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}
