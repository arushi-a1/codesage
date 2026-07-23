import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/authStore";

export default function LoginPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { login, register } = useAuthStore();
  const navigate = useNavigate();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (mode === "register") {
        await register(email, password, fullName);
        setMode("login");
        setError("Account created — sign in below.");
      } else {
        await login(email, password);
        navigate("/repositories");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh" }}>
      <div className="card" style={{ width: 380 }}>
        <h2 style={{ marginTop: 0 }}>CodeSage</h2>
        <div className="mode-tabs">
          <div className={`mode-tab ${mode === "login" ? "active" : ""}`} onClick={() => setMode("login")}>
            Sign in
          </div>
          <div className={`mode-tab ${mode === "register" ? "active" : ""}`} onClick={() => setMode("register")}>
            Create account
          </div>
        </div>
        <form className="form-stack" onSubmit={handleSubmit}>
          {mode === "register" && (
            <input placeholder="Full name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
          )}
          <input
            type="email"
            placeholder="Email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <input
            type="password"
            placeholder="Password (min 8 characters)"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error && <div className="error-text">{error}</div>}
          <button className="btn" type="submit" disabled={loading}>
            {loading ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>
      </div>
    </div>
  );
}
