import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { login } from "../api/auth";
import { useAuth } from "../auth/useAuth";

type LoginLocationState = {
    from?: {
        pathname: string;
    };
};

function dashboardForRole(role: "student" | "professor"): string {
    return role === "professor" ? "/teacher/class" : "/student/statistics";
}

export default function LoginPage() {
    const navigate = useNavigate();
    const location = useLocation();
    const { refreshUser } = useAuth();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [isSubmitting, setIsSubmitting] = useState(false);

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setError(null);

        const normalizedEmail = email.trim();
        if (normalizedEmail.length === 0 || password.length === 0) {
            setError("Enter your email and password.");
            return;
        }

        setIsSubmitting(true);
        try {
            const user = await login(normalizedEmail, password);
            await refreshUser();

            const state = location.state as LoginLocationState | null;
            const destination = state?.from?.pathname ?? dashboardForRole(user.role);
            navigate(destination, { replace: true });
        } catch {
            setError("The email or password is incorrect.");
        } finally {
            setIsSubmitting(false);
        }
    }

    return (
        <main className="login-page">
            <section className="login-card" aria-labelledby="login-heading">
                <h1 id="login-heading">Sign in to TechniView</h1>

                <form onSubmit={(event) => void handleSubmit(event)}>
                    <div className="form-field">
                        <label htmlFor="email">Email</label>
                        <input
                            autoComplete="email"
                            disabled={isSubmitting}
                            id="email"
                            name="email"
                            onChange={(event) => setEmail(event.target.value)}
                            required
                            type="email"
                            value={email}
                        />
                    </div>

                    <div className="form-field">
                        <label htmlFor="password">Password</label>
                        <input
                            autoComplete="current-password"
                            disabled={isSubmitting}
                            id="password"
                            name="password"
                            onChange={(event) => setPassword(event.target.value)}
                            required
                            type="password"
                            value={password}
                        />
                    </div>

                    {error && (
                        <p aria-live="assertive" className="form-error" role="alert">
                            {error}
                        </p>
                    )}

                    <button disabled={isSubmitting} type="submit">
                        {isSubmitting ? "Signing in..." : "Sign in"}
                    </button>
                </form>
            </section>
        </main>
    );
}
