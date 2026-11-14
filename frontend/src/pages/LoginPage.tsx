import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import "./LoginPage.css";
import logo from "../assets/TechniView_Logo_No_Title.png";
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
        <main className="tv-login tv-minimal">
            <header className="design-picker">
                <a className="login-logo" href="/login" aria-label="TechniView home">
                    <img src={logo} alt="TechniView" />
                </a>
            </header>

            <div className="login-stage">
                <section className="login-art" aria-label="TechniView introduction">
                    <div className="art-copy">
                        <span className="eyebrow">LEARN. BUILD. SEE CLEARLY.</span>
                        <h2>
                            Make your
                            <br />
                            next idea <em>work.</em>
                        </h2>
                        <p>A clearer view of your progress starts here.</p>
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
                            <span className="visual-caption">PROGRESS, IN FOCUS</span>
                        </div>
                        <span className="visual-tag tag-top">10101</span>
                        <span className="visual-tag tag-bottom">
                            &lt; learn by doing /&gt;
                        </span>
                    </div>
                    <div className="art-footer">
                        <span>YOUR WORKSPACE FOR WHAT’S NEXT</span>
                        <span>01 — 05</span>
                    </div>
                </section>

                <section className="login-form-side" aria-labelledby="login-heading">
                    <div className="form-wrap">
                        <div className="form-kicker">
                            <span className="status-dot" /> YOUR LEARNING SPACE
                        </div>
                        <h1 id="login-heading">
                            Welcome back<span className="title-period">.</span>
                        </h1>
                        <p className="form-intro">
                            Sign in to pick up where you left off.
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
                                <div className="field-label-row">
                                    <label htmlFor="password">Password</label>
                                    <Link to="/forgot-password">Forgot password?</Link>
                                </div>
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
                            <button
                                className="submit-login"
                                disabled={isSubmitting}
                                type="submit"
                            >
                                <span>
                                    {isSubmitting ? "Signing in..." : "Sign in"}
                                </span>
                                <span aria-hidden="true">↗</span>
                            </button>
                        </form>
                        <p className="auth-switch">
                            New to TechniView?{" "}
                            <Link to="/signup">Create an account</Link>
                        </p>
                        <div className="form-bottom">
                            <span className="bottom-rule" />{" "}
                            <span>SECURE ACCESS TO TECHNIVIEW</span>{" "}
                            <span className="bottom-rule" />
                        </div>
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
