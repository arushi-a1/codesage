import { Link } from "react-router-dom";
import { useAuthStore } from "../store/authStore";

export default function Sidebar() {
  const { email, logout } = useAuthStore();

  return (
    <div className="sidebar">
      <div className="brand">🧭 CodeSage</div>
      <Link to="/repositories">Repositories</Link>
      <div style={{ flex: 1 }} />
      <div className="muted">{email}</div>
      <button className="btn secondary" onClick={logout}>
        Sign out
      </button>
    </div>
  );
}
