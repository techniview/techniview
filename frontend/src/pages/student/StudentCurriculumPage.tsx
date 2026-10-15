import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getCurriculum, type CurriculumPool } from "../../api/curriculum";
import ErrorState from "../../components/ErrorState";
import LoadingState from "../../components/LoadingState";

export default function StudentCurriculumPage() {
    const [pools, setPools] = useState<CurriculumPool[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);

    useEffect(() => {
        let current = true;
        void getCurriculum()
            .then((items) => {
                if (current) setPools(items);
            })
            .catch(() => {
                if (current) setError(true);
            })
            .finally(() => {
                if (current) setLoading(false);
            });
        return () => {
            current = false;
        };
    }, []);

    if (loading) return <LoadingState message="Loading curriculum..." />;
    if (error) return <ErrorState message="We could not load the curriculum." />;

    const names = new Map(pools.map((pool) => [pool.slug, pool.name]));
    const problemNames = new Map(
        pools.flatMap((pool) =>
            pool.problems.map((item) => [item.problem.id, item.problem.title] as const),
        ),
    );

    return (
        <div className="student-curriculum-page">
            <header className="page-header">
                <p className="eyebrow">TechniView Trail</p>
                <h1>Curriculum</h1>
                <p>Complete prerequisite problems to unlock the next steps.</p>
            </header>
            {pools.map((pool) => (
                <section key={pool.slug} aria-labelledby={`pool-${pool.slug}`}>
                    <h2 id={`pool-${pool.slug}`}>
                        {pool.tier_name ? `${pool.tier_name}: ` : ""}
                        {pool.name}
                    </h2>
                    {pool.prerequisite_pool_slugs.length > 0 && (
                        <p>
                            Follows{" "}
                            {pool.prerequisite_pool_slugs
                                .map((slug) => names.get(slug) ?? slug)
                                .join(", ")}
                            .
                        </p>
                    )}
                    <ul>
                        {pool.problems.map((item) => (
                            <li key={item.problem.id}>
                                <Link to={`/student/problems/${item.problem.id}`}>
                                    {item.problem.title}
                                </Link>{" "}
                                <span>{item.status.replace("_", " ")}</span>
                                {item.recommended && <span> - Recommended next</span>}
                                {item.status === "locked" && (
                                    <span>
                                        {" "}
                                        Requires{" "}
                                        {item.prerequisite_problem_ids
                                            .map(
                                                (id) =>
                                                    problemNames.get(id) ??
                                                    `problem ${id}`,
                                            )
                                            .join(", ")}
                                    </span>
                                )}
                            </li>
                        ))}
                    </ul>
                </section>
            ))}
        </div>
    );
}
