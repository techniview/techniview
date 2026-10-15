import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { Course } from "../../api/analytics";
import { listCourses } from "../../api/courses";
import ErrorState from "../../components/ErrorState";
import LoadingState from "../../components/LoadingState";

async function studentCourses(): Promise<Course[]> {
    const courses: Course[] = [];
    let offset = 0;
    while (true) {
        const page = await listCourses(100, offset);
        courses.push(
            ...page.items.filter((item) => item.membership_role === "student"),
        );
        offset += page.items.length;
        if (page.items.length === 0 || offset >= page.total) {
            return courses;
        }
    }
}

export default function StudentCoursesPage() {
    const [courses, setCourses] = useState<Course[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let isCurrent = true;
        void studentCourses()
            .then((items) => {
                if (isCurrent) {
                    setCourses(items);
                }
            })
            .catch(() => {
                if (isCurrent) {
                    setError("We could not load your classes.");
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
    }, []);

    if (isLoading) {
        return <LoadingState message="Loading classes..." />;
    }
    if (error) {
        return <ErrorState message={error} />;
    }

    return (
        <div className="student-courses-page">
            <header className="page-header">
                <p className="eyebrow">Student dashboard</p>
                <h1>My Classes</h1>
            </header>
            {courses.length === 0 ? (
                <p>You are not in a class yet.</p>
            ) : (
                <ul>
                    {courses.map((course) => (
                        <li key={course.id}>
                            <Link to={`/student/courses/${course.id}`}>
                                {course.name}
                            </Link>
                            {course.withdrawn_at !== null
                                ? " (Withdrawn)"
                                : course.archived_at !== null
                                  ? " (Archived)"
                                  : ""}
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}
