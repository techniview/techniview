import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { getJoinPreview, type JoinPreview } from "../api/auth";
import { joinSignup } from "../api/courses";
import logo from "../assets/TechniView_Logo_No_Title.png";
import "./LoginPage.css";

function inviteToken(value: string): string {
    const trimmed = value.trim();
    try {
        const url = new URL(trimmed);
        const match = url.pathname.match(/\/join\/([^/]+)/);
        if (match?.[1]) return decodeURIComponent(match[1]);
    } catch {
        // The input can be a raw invite token rather than a full URL.
    }
    return trimmed;
}

export default function SignupPage() {
    const navigate = useNavigate();
    const { refreshUser } = useAuth();
    const [invite, setInvite] = useState("");
    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [passwordConfirm, setPasswordConfirm] = useState("");
    const [preview, setPreview] = useState<JoinPreview | null>(null);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    async function handleInviteBlur() {
        const token = inviteToken(invite);
        if (!token) {
            setPreview(null);
            return;
        }
        try {
            const result = await getJoinPreview(token);
            setPreview(result);
            setError(
                result.joinable ? null : "This class invitation is no longer active.",
            );
        } catch {
            setPreview(null);
            setError(
                "We could not find that class invitation. Check the code and try again.",
            );
        }
    }

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setError(null);
        if (password !== passwordConfirm) {
            setError("Passwords do not match.");
            return;
        }

        const token = inviteToken(invite);
        if (!token) {
            setError("Enter a class invite code to create your account.");
            return;
        }

        setIsSubmitting(true);
        try {
            const classPreview = preview ?? (await getJoinPreview(token));
            if (!classPreview.joinable) {
                setPreview(classPreview);
                setError("This class invitation is no longer active.");
                return;
            }
            setPreview(classPreview);
            await joinSignup(token, {
                name: name.trim(),
                email: email.trim(),
                password,
                password_confirm: passwordConfirm,
            });
            await refreshUser();
            navigate(`/student/courses/${classPreview.course_id}`, { replace: true });
        } catch {
            setError(
                "We could not create your account. Check the invitation and details, or sign in if you already have an account.",
            );
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
            <div className="login-stage signup-stage">
                <section className="login-art" aria-label="TechniView introduction">
                    <div className="art-copy">
                        <span className="eyebrow">YOUR NEXT CHAPTER</span>
                        <h2>
                            Learn by
                            <br />
                            building <em>together.</em>
                        </h2>
                        <p>Create your student account with a class invitation.</p>
                    </div>
                    <div className="art-footer">
                        <span>YOUR WORKSPACE FOR WHAT&apos;S NEXT</span>
                    </div>
                </section>
                <section className="login-form-side" aria-labelledby="signup-heading">
                    <div className="form-wrap">
                        <div className="form-kicker">
                            <span className="status-dot" /> STUDENT ACCOUNT
                        </div>
                        <h1 id="signup-heading">
                            Create your account<span className="title-period">.</span>
                        </h1>
                        <p className="form-intro">
                            Use the invite code from your teacher to join a class.
                        </p>
                        <form onSubmit={(event) => void handleSubmit(event)}>
                            <div className="tv-field">
                                <label htmlFor="signup-invite">
                                    Class invite code or link
                                </label>
                                <input
                                    autoComplete="off"
                                    disabled={isSubmitting}
                                    id="signup-invite"
                                    onBlur={() => void handleInviteBlur()}
                                    onChange={(event) => {
                                        setInvite(event.target.value);
                                        setPreview(null);
                                    }}
                                    placeholder="Paste your class invitation"
                                    required
                                    value={invite}
                                />
                            </div>
                            {preview?.joinable && (
                                <p className="signup-class-note">
                                    Joining <strong>{preview.name}</strong>
                                </p>
                            )}
                            <div className="tv-field">
                                <label htmlFor="signup-name">Full name</label>
                                <input
                                    autoComplete="name"
                                    disabled={isSubmitting}
                                    id="signup-name"
                                    maxLength={100}
                                    onChange={(event) => setName(event.target.value)}
                                    required
                                    value={name}
                                />
                            </div>
                            <div className="tv-field">
                                <label htmlFor="signup-email">Email address</label>
                                <input
                                    autoComplete="email"
                                    disabled={isSubmitting}
                                    id="signup-email"
                                    onChange={(event) => setEmail(event.target.value)}
                                    required
                                    type="email"
                                    value={email}
                                />
                            </div>
                            <div className="tv-field">
                                <label htmlFor="signup-password">Password</label>
                                <input
                                    autoComplete="new-password"
                                    disabled={isSubmitting}
                                    id="signup-password"
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
                                <label htmlFor="signup-password-confirm">
                                    Confirm password
                                </label>
                                <input
                                    autoComplete="new-password"
                                    disabled={isSubmitting}
                                    id="signup-password-confirm"
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
                                <span>
                                    {isSubmitting
                                        ? "Creating account..."
                                        : "Create account"}
                                </span>
                                <span aria-hidden="true">↗</span>
                            </button>
                        </form>
                        <p className="auth-switch">
                            Already have an account? <Link to="/login">Sign in</Link>
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
