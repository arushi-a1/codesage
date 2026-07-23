import { Navigate, Route, BrowserRouter as Router, Routes } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import { useAuthStore } from "./store/authStore";
import LoginPage from "./pages/LoginPage";
import RepositoriesPage from "./pages/RepositoriesPage";
import RepoChatPage from "./pages/RepoChatPage";

function RequireAuth({ children }: { children: JSX.Element }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return children;
}

function AppShell({ children }: { children: JSX.Element }) {
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main">{children}</div>
    </div>
  );
}

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/repositories"
          element={
            <RequireAuth>
              <AppShell>
                <RepositoriesPage />
              </AppShell>
            </RequireAuth>
          }
        />
        <Route
          path="/repositories/:repoId"
          element={
            <RequireAuth>
              <AppShell>
                <RepoChatPage />
              </AppShell>
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate to="/repositories" replace />} />
      </Routes>
    </Router>
  );
}
