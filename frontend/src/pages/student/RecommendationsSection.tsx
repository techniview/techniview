import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getRecommendations, type Recommendation } from "../../api/recommendations";

export default function RecommendationsSection() {
    const [items, setItems] = useState<Recommendation[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);

    useEffect(() => {
        let current = true;
        void getRecommendations()
            .then(({ items: recommendations }) => {
                if (current) setItems(recommendations);
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

    return (
        <section
            className="recommendations-section"
            aria-labelledby="recommendations-heading"
        >
            <div className="recommendations-heading">
                <h2 id="recommendations-heading">What to learn next</h2>
                <p>Practice beyond your classes, guided by your Trail progress.</p>
            </div>
            {loading ? (
                <p>Finding your next problems...</p>
            ) : error ? (
                <p>Recommendations are unavailable right now.</p>
            ) : items.length === 0 ? (
                <p>You have completed the available Trail problems.</p>
            ) : (
                <ul className="recommendations-list">
                    {items.map(({ problem, pool_name }) => (
                        <li key={problem.id}>
                            <span className="recommendation-technique">
                                {pool_name}
                            </span>
                            <Link to={`/student/problems/${problem.id}`}>
                                {problem.title}
                            </Link>
                            <span
                                className={`difficulty-pill difficulty-${problem.difficulty}`}
                            >
                                {problem.difficulty}
                            </span>
                        </li>
                    ))}
                </ul>
            )}
        </section>
    );
}
