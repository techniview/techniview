type ErrorStateProps = {
    message?: string;
    onRetry?: () => void;
};

export default function ErrorState({
    message = "Something went wrong. Please try again.",
    onRetry,
}: ErrorStateProps) {
    return (
        <section aria-live="assertive" className="error-state" role="alert">
            <h2>Unable to load this page</h2>
            <p>{message}</p>
            {onRetry && (
                <button onClick={onRetry} type="button">
                    Try again
                </button>
            )}
        </section>
    );
}
