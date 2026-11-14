import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { requestPasswordRecovery } from "../api/auth";
import logo from "../assets/TechniView_Logo_No_Title.png";
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
        <main className="tv-login tv-minimal">
            <header className="design-picker">
                <Link className="login-logo" to="/login" aria-label="TechniView home">
                    <img src={logo} alt="TechniView" />
                </Link>
            </header>
            <div className="login-stage">
                <section className="login-art" aria-label="TechniView introduction">
                    <div className="art-copy">
                        <span className="eyebrow">ACCOUNT SECURITY</span>
                        <h2>
                            Get back
                            <br />
                            to your <em>work.</em>
                        </h2>
                        <p>We&apos;ll help you get back into your learning space.</p>
                    </div>
                    <div className="art-footer">
                        <span>YOUR WORKSPACE FOR WHAT&apos;S NEXT</span>
                    </div>
                </section>
                <section className="login-form-side" aria-labelledby="recovery-heading">
                    <div className="form-wrap">
                        <div className="form-kicker">
                            <span className="status-dot" /> SECURE ACCOUNT RECOVERY
                        </div>
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
                                <span>
                                    {isSubmitting ? "Sending..." : "Send reset link"}
                                </span>
                                <span aria-hidden="true">↗</span>
                            </button>
                        </form>
                        <p className="auth-switch">
                            <Link to="/login">Back to sign in</Link>
                        </p>
                    </div>
                    <footer className="login-footer">
                        <span>© 2026 TechniView</span>
                        <span>Built for curious minds.</span>
                    </footer>
                </section>
            </div>
        </main>
    );
}
