import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getJoinPreview, joinLogin, joinSignup, type JoinPreview } from "../api/auth";
import { getCourse } from "../api/courses";
import { useAuth } from "../auth/useAuth";
import LoadingState from "../components/LoadingState";

export default function JoinPage() {
    const { token } = useParams();
    const navigate = useNavigate();
    const { refreshUser } = useAuth();
    const [preview, setPreview] = useState<JoinPreview | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [mode, setMode] = useState<"signup" | "login">("signup");
    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [passwordConfirm, setPasswordConfirm] = useState("");
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [message, setMessage] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!token) {
            setIsLoading(false);
            return;
        }
        let isCurrent = true;
        void getJoinPreview(token)
            .then((result) => {
                if (isCurrent) {
                    setPreview(result);
                }
            })
            .catch(() => {
                if (isCurrent) {
                    setError("This class link is invalid or has been revoked.");
                }
            })
            .finally(() => {
                if (isCurrent) {
                    setIsLoading(false);
                }
            });
        return () => {
            isCurrent = false;
        };
    }, [token]);

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!token || !preview?.joinable) {
            return;
        }
        if (mode === "signup" && password !== passwordConfirm) {
            setError("Passwords do not match.");
            return;
        }
        setError(null);
        setIsSubmitting(true);
        try {
            if (mode === "signup") {
                const response = await joinSignup(
                    token,
                    name.trim(),
                    email.trim(),
                    password,
                    passwordConfirm,
                );
                setMessage(response.message);
            } else {
                const response = await joinLogin(token, email.trim(), password);
                if ("message" in response) {
                    setMessage(response.message);
                } else {
                    await refreshUser();
                    const joinedCourse = await getCourse(preview.course_id);
                    navigate(
                        joinedCourse.membership_role !== "student"
                            ? "/teacher/class"
                            : `/student/courses/${preview.course_id}`,
                        { replace: true },
                    );
                }
            }
        } catch {
            setError(
                mode === "signup"
                    ? "We could not create your account. If you already have one, sign in instead."
                    : "We could not sign you in or join this class. Check your email and password.",
            );
        } finally {
            setIsSubmitting(false);
        }
    }

    if (isLoading) {
        return <LoadingState message="Checking class link..." />;
    }

    return (
        <main className="login-page">
            <section className="login-card" aria-labelledby="join-heading">
                <h1 id="join-heading">Join {preview?.name ?? "a class"}</h1>
                {preview?.description && <p>{preview.description}</p>}
                {!preview ? (
                    <p role="alert">{error ?? "This class link is unavailable."}</p>
                ) : !preview.joinable ? (
                    <p role="alert">
                        This class is archived and cannot accept new students.
                    </p>
                ) : message ? (
                    <p role="status">{message}</p>
                ) : (
                    <>
                        <p>
                            <button
                                aria-pressed={mode === "signup"}
                                onClick={() => {
                                    setMode("signup");
                                    setError(null);
                                }}
                                type="button"
                            >
                                Create account
                            </button>{" "}
                            <button
                                aria-pressed={mode === "login"}
                                onClick={() => {
                                    setMode("login");
                                    setError(null);
                                }}
                                type="button"
                            >
                                Sign in
                            </button>
                        </p>
                        <form onSubmit={(event) => void handleSubmit(event)}>
                            {mode === "signup" && (
                                <div className="form-field">
                                    <label htmlFor="join-name">Name</label>
                                    <input
                                        autoComplete="name"
                                        disabled={isSubmitting}
                                        id="join-name"
                                        maxLength={100}
                                        onChange={(event) =>
                                            setName(event.target.value)
                                        }
                                        required
                                        value={name}
                                    />
                                </div>
                            )}
                            <div className="form-field">
                                <label htmlFor="join-email">Email</label>
                                <input
                                    autoComplete="email"
                                    disabled={isSubmitting}
                                    id="join-email"
                                    onChange={(event) => setEmail(event.target.value)}
                                    required
                                    type="email"
                                    value={email}
                                />
                            </div>
                            <div className="form-field">
                                <label htmlFor="join-password">Password</label>
                                <input
                                    autoComplete={
                                        mode === "signup"
                                            ? "new-password"
                                            : "current-password"
                                    }
                                    disabled={isSubmitting}
                                    id="join-password"
                                    minLength={mode === "signup" ? 8 : undefined}
                                    onChange={(event) =>
                                        setPassword(event.target.value)
                                    }
                                    required
                                    type="password"
                                    value={password}
                                />
                            </div>
                            {mode === "signup" && (
                                <div className="form-field">
                                    <label htmlFor="join-password-confirm">
                                        Confirm password
                                    </label>
                                    <input
                                        autoComplete="new-password"
                                        disabled={isSubmitting}
                                        id="join-password-confirm"
                                        minLength={8}
                                        onChange={(event) =>
                                            setPasswordConfirm(event.target.value)
                                        }
                                        required
                                        type="password"
                                        value={passwordConfirm}
                                    />
                                </div>
                            )}
                            {error && (
                                <p className="form-error" role="alert">
                                    {error}
                                </p>
                            )}
                            <button disabled={isSubmitting} type="submit">
                                {isSubmitting
                                    ? "Please wait..."
                                    : mode === "signup"
                                      ? "Create account"
                                      : "Sign in and join"}
                            </button>
                        </form>
                    </>
                )}
                <p>
                    <Link to="/login">Back to sign in</Link>
                </p>
            </section>
        </main>
    );
}
