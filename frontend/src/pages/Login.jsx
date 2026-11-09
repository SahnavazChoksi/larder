import { useState } from "react";
import { errorText } from "../api";
import { useAuth } from "../auth";

export default function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(username.trim(), password);
    } catch (err) {
      setError(err.response?.status === 401 ? "Wrong username or password." : errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <form onSubmit={submit}>
        <div className="brand">
          <div className="brand-mark">L</div>
          <div>
            <b>Larder</b>
            <span>Restaurant back office</span>
          </div>
        </div>
        <label className="f">
          Username
          <input id="username" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
        </label>
        <label className="f">
          Password
          <input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {error && <div className="note error">{error}</div>}
        <button className="btn primary" type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <p className="small muted" style={{ margin: 0 }}>
          Demo accounts are listed after running <code>python manage.py seed_demo</code>.
        </p>
      </form>
    </div>
  );
}
