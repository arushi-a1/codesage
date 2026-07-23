import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Repository } from "../api/client";

export default function RepositoriesPage() {
  const [repos, setRepos] = useState<Repository[]>([]);
  const [githubUrl, setGithubUrl] = useState("");
  const [branch, setBranch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);

  async function refresh() {
    setRepos(await api.listRepositories());
  }

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 4000); // poll for indexing progress
    return () => clearInterval(interval);
  }, []);

  async function handleImport(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setImporting(true);
    try {
      await api.importRepository(githubUrl, branch || undefined);
      setGithubUrl("");
      setBranch("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setImporting(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this repository and its index?")) return;
    await api.deleteRepository(id);
    await refresh();
  }

  return (
    <div>
      <h2>Repositories</h2>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Import a GitHub repository</h3>
        <form className="form-stack" onSubmit={handleImport}>
          <input
            placeholder="https://github.com/owner/repo"
            required
            value={githubUrl}
            onChange={(e) => setGithubUrl(e.target.value)}
          />
          <input
            placeholder="Branch (optional, defaults to main)"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
          />
          {error && <div className="error-text">{error}</div>}
          <button className="btn" type="submit" disabled={importing}>
            {importing ? "Importing…" : "Import & index"}
          </button>
        </form>
      </div>

      <div className="repo-list">
        {repos.map((repo) => (
          <div className="repo-row" key={repo.id}>
            <div>
              <div style={{ fontWeight: 600 }}>{repo.full_name}</div>
              <div className="muted">
                {repo.file_count} files · {repo.chunk_count} chunks
              </div>
              {repo.status !== "ready" && <div className="muted">{repo.status_detail}</div>}
            </div>
            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <span className={`badge ${repo.status}`}>{repo.status}</span>
              {repo.status === "ready" && (
                <Link className="btn secondary" to={`/repositories/${repo.id}`}>
                  Open
                </Link>
              )}
              <button className="btn secondary" onClick={() => handleDelete(repo.id)}>
                Delete
              </button>
            </div>
          </div>
        ))}
        {repos.length === 0 && <div className="muted">No repositories yet — import one above.</div>}
      </div>
    </div>
  );
}
