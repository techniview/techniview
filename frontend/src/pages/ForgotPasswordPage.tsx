import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { requestPasswordRecovery } from "../api/auth";

export default function ForgotPasswordPage() {
    const [email, setEmail] = useState("");
    const [message, setMessage] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [isSubmitting, setIsSubmitting] = useState(false);

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setError(null);
        setMessage(null);
        setIsSubmitting(true);
        try {
            const response = await requestPasswordRecovery(email.trim());
            setMessage(response.message);
        } catch {
            setError("We could not process your request. Please try again.");
        } finally {
            setIsSubmitting(false);
        }
    }

    return (
        <main className="login-page">
            <section className="login-card" aria-labelledby="recovery-heading">
                <h1 id="recovery-heading">Reset your password</h1>
                <p>
                    Enter your account email. We will send a reset link if it is
                    eligible.
                </p>
                <form onSubmit={(event) => void handleSubmit(event)}>
                    <div className="form-field">
                        <label htmlFor="recovery-email">Email</label>
                        <input
                            autoComplete="email"
                            disabled={isSubmitting}
                            id="recovery-email"
                            onChange={(event) => setEmail(event.target.value)}
                            required
                            type="email"
                            value={email}
                        />
                    </div>
                    {error && (
                        <p className="form-error" role="alert">
                            {error}
                        </p>
                    )}
                    {message && <p role="status">{message}</p>}
                    <button disabled={isSubmitting} type="submit">
                        {isSubmitting ? "Sending..." : "Send reset link"}
                    </button>
                </form>
                <p>
                    <Link to="/login">Back to sign in</Link>
                </p>
            </section>
        </main>
    );
}
