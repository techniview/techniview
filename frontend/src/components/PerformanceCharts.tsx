import type { AnalyticsMetrics } from "../types/analytics";
import "./PerformanceCharts.css";

const errorLabels: Array<[keyof AnalyticsMetrics["errors"], string]> = [
    ["wrong_answer", "Wrong answer"],
    ["compile_error", "Compile error"],
    ["runtime_error", "Runtime error"],
    ["timeout", "Time limit"],
    ["resource_limit", "Resource limit"],
];

export default function PerformanceCharts({ metrics }: { metrics: AnalyticsMetrics }) {
    const rate = metrics.completion_rate;
    const percent =
        rate === null ? 0 : Math.round(Math.max(0, Math.min(1, rate)) * 100);
    const maxError = Math.max(1, ...errorLabels.map(([key]) => metrics.errors[key]));
    const hasErrors = errorLabels.some(([key]) => metrics.errors[key] > 0);

    return (
        <section
            className="performance-charts"
            aria-labelledby="performance-charts-heading"
        >
            <div className="performance-charts-heading">
                <h2 id="performance-charts-heading">Progress and attempts</h2>
            </div>
            <div className="performance-chart-grid">
                <div className="performance-chart-section">
                    <h3>Completion rate</h3>
                    <div className="completion-chart-row">
                        <div
                            className="completion-ring"
                            role="img"
                            aria-label={
                                rate === null
                                    ? "No completion data"
                                    : `${percent}% completion rate`
                            }
                            style={
                                {
                                    "--completion-percent": `${percent}%`,
                                } as React.CSSProperties
                            }
                        >
                            <span>{rate === null ? "--" : `${percent}%`}</span>
                        </div>
                        <div className="completion-chart-labels">
                            <p>
                                <strong>{metrics.completed_count}</strong> completed
                            </p>
                            <p>
                                <strong>{metrics.started_count}</strong> started
                            </p>
                            <p>
                                <strong>{metrics.assigned_count}</strong> assigned
                            </p>
                        </div>
                    </div>
                </div>
                <div className="performance-chart-section">
                    <h3>Attempt errors</h3>
                    {hasErrors ? (
                        <ul className="error-chart">
                            {errorLabels.map(([key, label]) => (
                                <li key={key}>
                                    <span>{label}</span>
                                    <div
                                        className="error-chart-track"
                                        aria-hidden="true"
                                    >
                                        <div
                                            style={{
                                                width: `${(metrics.errors[key] / maxError) * 100}%`,
                                            }}
                                        />
                                    </div>
                                    <strong>{metrics.errors[key]}</strong>
                                </li>
                            ))}
                        </ul>
                    ) : (
                        <p className="chart-empty">No attempt errors in this view.</p>
                    )}
                </div>
            </div>
        </section>
    );
}
