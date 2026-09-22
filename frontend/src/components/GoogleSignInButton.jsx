import { useState } from "react";

export default function GoogleSignInButton() {
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState("");

    async function handleSignIn() {
        setBusy(true);
        setMessage("Signing in with Google...");
    }
    return (
        <section>
        <button onClick={handleSignIn} disabled={busy}>
            {busy ? "Signing in..." : "Sign in with Google"}
        </button>
        {<p role="status">{message}</p>}
        </section>
    );
}