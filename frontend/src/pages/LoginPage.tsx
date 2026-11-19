import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import "./LoginPage.css";
import BrandLogo from "../components/BrandLogo";
import { login } from "../api/auth";
import { useAuth } from "../auth/useAuth";

function dashboardForRole(role: "student" | "professor"): string {
    return role === "professor" ? "/teacher/classes" : "/student/courses";
}

export default function LoginPage() {
    const navigate = useNavigate();
    const { refreshUser } = useAuth();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [isSubmitting, setIsSubmitting] = useState(false);

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setError(null);
        const normalizedEmail = email.trim();
        if (!normalizedEmail || !password) {
            setError("Enter your email and password.");
            return;
        }
        setIsSubmitting(true);
        try {
            const user = await login(normalizedEmail, password);
            await refreshUser();
            navigate(dashboardForRole(user.role), { replace: true });
        } catch {
            setError("The email or password is incorrect.");
        } finally {
            setIsSubmitting(false);
        }
    }

    return (
        <main className="tv-login tv-minimal login-main">
            <header className="design-picker">
                <a className="login-logo" href="/login" aria-label="TechniView home">
                    <BrandLogo />
                </a>
            </header>

            <div className="login-stage">
                <section className="login-art" aria-label="TechniView introduction">
                    <div className="login-art-top">
                        <a
                            className="login-logo"
                            href="/login"
                            aria-label="TechniView home"
                        >
                            <BrandLogo />
                        </a>
                    </div>
                    <div className="art-copy">
                        <h2>
                            Solve problems.
                            <br />
                            See your <em>progress.</em>
                        </h2>
                        <p>
                            Practice technical interviewing in Python through your
                            coursework.
                        </p>
                    </div>
                    <div className="art-visual" aria-hidden="true">
                        <div className="orbit orbit-one" />
                        <div className="orbit orbit-two" />
                        <div className="visual-card">
                            <span className="visual-dot" />
                            <span className="visual-line line-long" />
                            <span className="visual-line" />
                            <div className="visual-chart">
                                <i />
                                <i />
                                <i />
                                <i />
                                <i />
                                <i />
                                <i />
                            </div>
                            <span className="visual-caption">PROBLEM PROGRESS</span>
                        </div>
                        <span className="visual-tag tag-top">10101</span>
                        <span className="visual-tag tag-bottom">
                            &lt; solve, test, learn /&gt;
                        </span>
                    </div>
                </section>

                <section className="login-form-side" aria-labelledby="login-heading">
                    <div className="form-wrap">
                        <h1 id="login-heading">
                            Welcome back<span className="title-period">.</span>
                        </h1>
                        <p className="form-intro">
                            Sign in to continue your coding practice.
                        </p>
                        <form onSubmit={(event) => void handleSubmit(event)}>
                            <div className="tv-field">
                                <label htmlFor="email">Email address</label>
                                <input
                                    autoComplete="email"
                                    disabled={isSubmitting}
                                    id="email"
                                    name="email"
                                    onChange={(event) => setEmail(event.target.value)}
                                    placeholder="you@example.edu"
                                    required
                                    type="email"
                                    value={email}
                                />
                            </div>
                            <div className="tv-field">
                                <label htmlFor="password">Password</label>
                                <input
                                    autoComplete="current-password"
                                    disabled={isSubmitting}
                                    id="password"
                                    name="password"
                                    onChange={(event) =>
                                        setPassword(event.target.value)
                                    }
                                    placeholder="Enter your password"
                                    required
                                    type="password"
                                    value={password}
                                />
                            </div>
                            {error && (
                                <p
                                    aria-live="assertive"
                                    className="tv-error"
                                    role="alert"
                                >
                                    {error}
                                </p>
                            )}
                            <div className="login-actions">
                                <button
                                    className="submit-login"
                                    disabled={isSubmitting}
                                    type="submit"
                                >
                                    {isSubmitting ? "Signing in..." : "Sign in"}
                                </button>
                                <Link
                                    className="auth-secondary-link"
                                    to="/forgot-password"
                                >
                                    Forgot Password?
                                </Link>
                            </div>
                        </form>
                        <p className="auth-switch">
                            New to TechniView?{" "}
                            <Link to="/signup">Create an account</Link>
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
