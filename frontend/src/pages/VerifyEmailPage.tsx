import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { verifyEmail } from "../api/auth";

export default function VerifyEmailPage() {
    const [searchParams] = useSearchParams();
    const token = searchParams.get("token");
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [isComplete, setIsComplete] = useState(false);
    const [error, setError] = useState<string | null>(null);

    async function handleVerify() {
        if (!token) {
            return;
        }
        setError(null);
        setIsSubmitting(true);
        try {
            await verifyEmail(token);
            setIsComplete(true);
        } catch {
            setError("This verification link is invalid or expired.");
        } finally {
            setIsSubmitting(false);
        }
    }

    return (
        <main className="login-page">
            <section className="login-card" aria-labelledby="verify-heading">
                <h1 id="verify-heading">Verify your email</h1>
                {!token ? (
                    <p role="alert">This verification link is missing its token.</p>
                ) : isComplete ? (
                    <p role="status">Your email is verified. You can now sign in.</p>
                ) : (
                    <>
                        <p>Confirm your email to finish creating your account.</p>
                        {error && (
                            <p className="form-error" role="alert">
                                {error}
                            </p>
                        )}
                        <button
                            disabled={isSubmitting}
                            onClick={() => void handleVerify()}
                            type="button"
                        >
                            {isSubmitting ? "Verifying..." : "Verify email"}
                        </button>
                    </>
                )}
                <p>
                    <Link to="/login">Go to sign in</Link>
                </p>
            </section>
        </main>
    );
}
