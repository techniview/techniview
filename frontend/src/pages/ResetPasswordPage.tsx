import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { resetPassword } from "../api/auth";
import { useAuth } from "../auth/useAuth";
import BrandLogo from "../components/BrandLogo";
import "./LoginPage.css";

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
        if (!token) return;
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
        <main className="tv-login tv-minimal">
            <header className="design-picker">
                <Link className="login-logo" to="/login" aria-label="TechniView home">
                    <BrandLogo />
                </Link>
            </header>
            <div className="login-stage">
                <section className="login-art" aria-label="TechniView introduction">
                    <div className="art-copy">
                        <h2>
                            A fresh
                            <br />
                            start for your <em>account.</em>
                        </h2>
                        <p>Choose a new password to get back to your work.</p>
                    </div>
                </section>
                <section className="login-form-side" aria-labelledby="reset-heading">
                    <div className="form-wrap">
                        <h1 id="reset-heading">
                            Choose a new password<span className="title-period">.</span>
                        </h1>
                        {!token ? (
                            <p className="form-intro" role="alert">
                                This reset link is missing its token.
                            </p>
                        ) : isComplete ? (
                            <>
                                <p className="form-intro" role="status">
                                    Your password was changed. Sign in with the new
                                    password.
                                </p>
                                <Link className="auth-primary-link" to="/login">
                                    Go to sign in
                                </Link>
                            </>
                        ) : (
                            <>
                                <p className="form-intro">
                                    Use at least 8 characters for your new password.
                                </p>
                                <form onSubmit={(event) => void handleSubmit(event)}>
                                    <div className="tv-field">
                                        <label htmlFor="new-password">
                                            New password
                                        </label>
                                        <input
                                            autoComplete="new-password"
                                            disabled={isSubmitting}
                                            id="new-password"
                                            minLength={8}
                                            onChange={(event) =>
                                                setPassword(event.target.value)
                                            }
                                            required
                                            type="password"
                                            value={password}
                                        />
                                    </div>
                                    <div className="tv-field">
                                        <label htmlFor="confirm-password">
                                            Confirm password
                                        </label>
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
                                        <p className="tv-error" role="alert">
                                            {error}
                                        </p>
                                    )}
                                    <button
                                        className="submit-login"
                                        disabled={isSubmitting}
                                        type="submit"
                                    >
                                        {isSubmitting
                                            ? "Changing password..."
                                            : "Change password"}
                                    </button>
                                </form>
                                <p className="auth-switch">
                                    <Link to="/forgot-password">
                                        Request a new reset link
                                    </Link>
                                </p>
                            </>
                        )}
                    </div>
                    <footer className="login-footer">
                        <span>© 2026 TechniView</span>
                        <Link to="/login">Back to sign in</Link>
                    </footer>
                </section>
            </div>
        </main>
    );
}
