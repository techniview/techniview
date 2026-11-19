import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { requestPasswordRecovery } from "../api/auth";
import BrandLogo from "../components/BrandLogo";
import "./LoginPage.css";

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
        <main className="tv-login tv-minimal login-main">
            <header className="design-picker">
                <Link className="login-logo" to="/login" aria-label="TechniView home">
                    <BrandLogo />
                </Link>
            </header>
            <div className="login-stage">
                <section className="login-art" aria-label="TechniView introduction">
                    <div className="login-art-top">
                        <Link
                            className="login-logo"
                            to="/login"
                            aria-label="TechniView home"
                        >
                            <BrandLogo />
                        </Link>
                    </div>
                    <div className="art-copy">
                        <h2>
                            Get back
                            <br />
                            to your <em>work.</em>
                        </h2>
                        <p>We&apos;ll help you get back into your learning space.</p>
                    </div>
                </section>
                <section className="login-form-side" aria-labelledby="recovery-heading">
                    <div className="form-wrap">
                        <h1 id="recovery-heading">
                            Reset your password<span className="title-period">.</span>
                        </h1>
                        <p className="form-intro">
                            Enter your account email. We&apos;ll send a reset link if
                            the account is eligible.
                        </p>
                        <form onSubmit={(event) => void handleSubmit(event)}>
                            <div className="tv-field">
                                <label htmlFor="recovery-email">Email address</label>
                                <input
                                    autoComplete="email"
                                    disabled={isSubmitting}
                                    id="recovery-email"
                                    onChange={(event) => setEmail(event.target.value)}
                                    placeholder="you@example.edu"
                                    required
                                    type="email"
                                    value={email}
                                />
                            </div>
                            {error && (
                                <p className="tv-error" role="alert">
                                    {error}
                                </p>
                            )}
                            {message && (
                                <p className="signup-class-note" role="status">
                                    {message}
                                </p>
                            )}
                            <button
                                className="submit-login"
                                disabled={isSubmitting}
                                type="submit"
                            >
                                {isSubmitting ? "Sending..." : "Send reset link"}
                            </button>
                        </form>
                        <p className="auth-switch">
                            <Link to="/login">Back to sign in</Link>
                        </p>
                    </div>
                    <footer className="login-footer">
                        <span>© 2026 TechniView</span>
                    </footer>
                </section>
            </div>
        </main>
    );
}
