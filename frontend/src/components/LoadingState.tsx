type LoadingStateProps = {
    message?: string;
};

export default function LoadingState({ message = "Loading..." }: LoadingStateProps) {
    return (
        <div
            aria-busy="true"
            aria-live="polite"
            className="loading-state"
            role="status"
        >
            <span aria-hidden="true" className="loading-state-spinner" />
            <span>{message}</span>
        </div>
    );
}
