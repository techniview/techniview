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
    const tiers = new Map<string, { tier: number | null; pools: CurriculumPool[] }>();
    for (const pool of pools) {
        const tierName = pool.tier_name ?? "Optional Extensions";
        const group = tiers.get(tierName) ?? { tier: pool.tier, pools: [] };
        group.pools.push(pool);
        tiers.set(tierName, group);
    }

    return (
        <div className="student-curriculum-page">
            <header className="page-header">
                <p className="eyebrow">TechniView Trail</p>
                <h1>Trail</h1>
                <p>
                    Practice by tier and technique. Complete one problem in each
                    prerequisite pool to get a recommendation from the next pool.
                </p>
            </header>
            {[...tiers].map(([tierName, group]) => (
                <section
                    key={tierName}
                    aria-labelledby={`tier-${group.tier ?? "optional"}`}
                >
                    <h2 id={`tier-${group.tier ?? "optional"}`}>
                        {group.tier ? `Tier ${group.tier}: ` : ""}
                        {tierName}
                    </h2>
                    {group.pools.map((pool) => (
                        <section key={pool.slug} aria-labelledby={`pool-${pool.slug}`}>
                            <h3 id={`pool-${pool.slug}`}>{pool.name}</h3>
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
                                        <Link
                                            to={`/student/problems/${item.problem.id}`}
                                        >
                                            {item.problem.title}
                                        </Link>{" "}
                                        <span>{item.status.replace("_", " ")}</span>
                                        {item.recommended && (
                                            <span> - Recommended next</span>
                                        )}
                                    </li>
                                ))}
                            </ul>
                        </section>
                    ))}
                </section>
            ))}
        </div>
    );
}
