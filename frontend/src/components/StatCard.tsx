type StatCardProps = {
    label: string;
    value: string;
};

export default function StatCard({ label, value }: StatCardProps) {
    return (
        <article className="stat-card">
            <p className="stat-card-label">{label}</p>
            <p className="stat-card-value">{value}</p>
        </article>
    );
}
