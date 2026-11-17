import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { getCurriculum, type CurriculumPool } from "../../api/curriculum";
import ErrorState from "../../components/ErrorState";
import LoadingState from "../../components/LoadingState";
import RecommendationsSection from "./RecommendationsSection";

function TrailPoolCard({ pool }: { pool: CurriculumPool }) {
    const dialogRef = useRef<HTMLDialogElement>(null);
    const completed = pool.problems.filter(
        (item) => item.status === "completed",
    ).length;
    const percent = pool.problems.length ? (completed / pool.problems.length) * 100 : 0;

    return (
        <li className="trail-card">
            <div className="trail-card-heading">
                <h3>{pool.name}</h3>
                <span>
                    {completed}/{pool.problems.length} done
                </span>
            </div>
            <div
                className="trail-progress"
                role="progressbar"
                aria-label={`${pool.name} completion`}
                aria-valuenow={completed}
                aria-valuemin={0}
                aria-valuemax={pool.problems.length}
            >
                <span style={{ width: `${percent}%` }} />
            </div>
            <button
                className="trail-open"
                onClick={() => dialogRef.current?.showModal()}
                type="button"
            >
                View {pool.problems.length} problems
            </button>
            <dialog
                aria-labelledby={`pool-${pool.slug}`}
                className="trail-dialog"
                ref={dialogRef}
            >
                <div className="trail-dialog-header">
                    <div>
                        <h3 id={`pool-${pool.slug}`}>{pool.name}</h3>
                        <p>
                            Choose any problem. Your progress updates after you solve
                            it.
                        </p>
                    </div>
                    <button
                        aria-label="Close problem list"
                        className="trail-close"
                        onClick={() => dialogRef.current?.close()}
                        type="button"
                    >
                        Close
                    </button>
                </div>
                <ul>
                    {pool.problems.map((item) => (
                        <li key={item.problem.id}>
                            <Link to={`/student/problems/${item.problem.id}`}>
                                {item.problem.title}
                            </Link>
                            <span>{item.status.replace("_", " ")}</span>
                        </li>
                    ))}
                </ul>
            </dialog>
        </li>
    );
}

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
                <h1>TechniView Trail</h1>
                <p>
                    Explore techniques in any order. Each bar tracks problems you have
                    completed; suggestions help you choose what to try next.
                </p>
            </header>
            <RecommendationsSection />
            <div className="trail-map">
                {[...tiers].map(([tierName, group]) => (
                    <section
                        className="trail-tier"
                        key={tierName}
                        aria-labelledby={`tier-${group.tier ?? "optional"}`}
                    >
                        <h2 id={`tier-${group.tier ?? "optional"}`}>{tierName}</h2>
                        <ul className="trail-steps">
                            {group.pools.map((pool) => (
                                <TrailPoolCard key={pool.slug} pool={pool} />
                            ))}
                        </ul>
                    </section>
                ))}
            </div>
        </div>
    );
}
