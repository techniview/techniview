import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { resetPassword } from "../api/auth";
import { useAuth } from "../auth/useAuth";

export default function ResetPasswordPage() {
    const [searchParams] = useSearchParams();
    const token = searchParams.get("token");
    const { refreshUser } = useAuth();
    const [password, setPassword] = useState("");
    const [passwordConfirm, setPasswordConfirm] = useState("");
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [isComplete, setIsComplete] = useState(false);
    const [error, setError] = useState<string | null>(null);

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!token) {
            return;
        }
        if (password !== passwordConfirm) {
            setError("Passwords do not match.");
            return;
        }
        setError(null);
        setIsSubmitting(true);
        try {
            await resetPassword(token, password, passwordConfirm);
            await refreshUser();
            setIsComplete(true);
        } catch {
            setError("This reset link is invalid or expired. Request a new one.");
        } finally {
            setIsSubmitting(false);
        }
    }

    return (
        <main className="login-page">
            <section className="login-card" aria-labelledby="reset-heading">
                <h1 id="reset-heading">Choose a new password</h1>
                {!token ? (
                    <p role="alert">This reset link is missing its token.</p>
                ) : isComplete ? (
                    <p role="status">
                        Your password was changed. Sign in with the new password.
                    </p>
                ) : (
                    <form onSubmit={(event) => void handleSubmit(event)}>
                        <div className="form-field">
                            <label htmlFor="new-password">New password</label>
                            <input
                                autoComplete="new-password"
                                disabled={isSubmitting}
                                id="new-password"
                                minLength={8}
                                onChange={(event) => setPassword(event.target.value)}
                                required
                                type="password"
                                value={password}
                            />
                        </div>
                        <div className="form-field">
                            <label htmlFor="confirm-password">Confirm password</label>
                            <input
                                autoComplete="new-password"
                                disabled={isSubmitting}
                                id="confirm-password"
                                minLength={8}
                                onChange={(event) =>
                                    setPasswordConfirm(event.target.value)
                                }
                                required
                                type="password"
                                value={passwordConfirm}
                            />
                        </div>
                        {error && (
                            <p className="form-error" role="alert">
                                {error}
                            </p>
                        )}
                        <button disabled={isSubmitting} type="submit">
                            {isSubmitting ? "Changing..." : "Change password"}
                        </button>
                    </form>
                )}
                <p>
                    <Link to={token && !isComplete ? "/forgot-password" : "/login"}>
                        {token && !isComplete ? "Request a new link" : "Go to sign in"}
                    </Link>
                </p>
            </section>
        </main>
    );
}
