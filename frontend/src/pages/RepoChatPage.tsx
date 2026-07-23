import { FormEvent, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  api,
  ChatMessage,
  Citation,
  Repository,
  reviewPullRequest,
  sendChatMessage,
} from "../api/client";

const MODES: { id: string; label: string }[] = [
  { id: "chat", label: "Chat" },
  { id: "codegen", label: "Generate code" },
  { id: "bug_detection", label: "Find bugs" },
  { id: "architecture", label: "Architecture" },
  { id: "refactor", label: "Refactor" },
];

interface DisplayMessage {
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  streaming?: boolean;
}

export default function RepoChatPage() {
  const { repoId } = useParams<{ repoId: string }>();
  const [repo, setRepo] = useState<Repository | null>(null);
  const [mode, setMode] = useState("chat");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [prNumber, setPrNumber] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!repoId) return;
    api.getRepository(repoId).then(setRepo);
  }, [repoId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function ensureSession() {
    if (!repoId) return null;
    if (sessionId) return sessionId;
    const session = await api.createChatSession(repoId, mode);
    setSessionId(session.id);
    return session.id;
  }

  async function switchMode(newMode: string) {
    setMode(newMode);
    setSessionId(null);
    setMessages([]);
  }

  async function handleSend(e: FormEvent) {
    e.preventDefault();
    if (!input.trim() || busy) return;
    setError(null);
    const userText = input;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userText, citations: [] }]);
    setMessages((prev) => [...prev, { role: "assistant", content: "", citations: [], streaming: true }]);
    setBusy(true);

    try {
      const sid = await ensureSession();
      if (!sid) throw new Error("Could not create chat session");

      await sendChatMessage(sid, userText, (event) => {
        if (event.type === "citations" && event.citations) {
          setMessages((prev) => updateLastAssistant(prev, (m) => ({ ...m, citations: event.citations! })));
        } else if (event.type === "token" && event.content) {
          setMessages((prev) =>
            updateLastAssistant(prev, (m) => ({ ...m, content: m.content + event.content })),
          );
        } else if (event.type === "error") {
          setError(event.message ?? "Stream error");
        } else if (event.type === "done") {
          setMessages((prev) => updateLastAssistant(prev, (m) => ({ ...m, streaming: false })));
        }
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message");
    } finally {
      setBusy(false);
    }
  }

  async function handleReviewPR(e: FormEvent) {
    e.preventDefault();
    const n = parseInt(prNumber, 10);
    if (!repoId || Number.isNaN(n) || busy) return;
    setError(null);
    setMessages((prev) => [
      ...prev,
      { role: "user", content: `Review PR #${n}`, citations: [] },
      { role: "assistant", content: "", citations: [], streaming: true },
    ]);
    setBusy(true);
    try {
      await reviewPullRequest(repoId, n, (event) => {
        if (event.type === "token" && event.content) {
          setMessages((prev) =>
            updateLastAssistant(prev, (m) => ({ ...m, content: m.content + event.content })),
          );
        } else if (event.type === "error") {
          setError(event.message ?? "Stream error");
        } else if (event.type === "done") {
          setMessages((prev) => updateLastAssistant(prev, (m) => ({ ...m, streaming: false })));
        }
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "PR review failed");
    } finally {
      setBusy(false);
    }
  }

  if (!repo) return <div className="muted">Loading repository…</div>;

  return (
    <div className="chat-layout">
      <h2 style={{ marginBottom: 4 }}>{repo.full_name}</h2>
      <div className="muted" style={{ marginBottom: 12 }}>
        {repo.file_count} files indexed · {repo.chunk_count} chunks
      </div>

      <div className="mode-tabs">
        {MODES.map((m) => (
          <div key={m.id} className={`mode-tab ${mode === m.id ? "active" : ""}`} onClick={() => switchMode(m.id)}>
            {m.label}
          </div>
        ))}
        <div className={`mode-tab ${mode === "pr_review" ? "active" : ""}`} onClick={() => switchMode("pr_review")}>
          Review PR
        </div>
      </div>

      <div className="chat-messages">
        {messages.map((m, i) => (
          <div key={i} className={`chat-message ${m.role}`}>
            {m.content || (m.streaming ? "…" : "")}
            {m.citations.length > 0 && (
              <div className="citations">
                {m.citations.map((c, ci) => (
                  <span key={ci} className="citation-chip">
                    {c.path}:{c.start_line}-{c.end_line}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {error && <div className="error-text">{error}</div>}

      {mode === "pr_review" ? (
        <form className="chat-input-row" onSubmit={handleReviewPR}>
          <input
            placeholder="PR number, e.g. 42"
            value={prNumber}
            onChange={(e) => setPrNumber(e.target.value)}
          />
          <button className="btn" disabled={busy}>
            {busy ? "Reviewing…" : "Review"}
          </button>
        </form>
      ) : (
        <form className="chat-input-row" onSubmit={handleSend}>
          <input
            placeholder={placeholderFor(mode)}
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
          <button className="btn" disabled={busy}>
            {busy ? "Thinking…" : "Send"}
          </button>
        </form>
      )}
    </div>
  );
}

function placeholderFor(mode: string): string {
  switch (mode) {
    case "codegen":
      return "Describe the change you want, e.g. 'add input validation to the signup form'";
    case "bug_detection":
      return "Point at an area to check, or leave blank to scan broadly";
    case "architecture":
      return "Ask about a module, or 'explain the overall architecture'";
    case "refactor":
      return "Point at code that feels messy, e.g. 'services/payments.py'";
    default:
      return "Ask a question about this codebase…";
  }
}

function updateLastAssistant(
  messages: DisplayMessage[],
  updater: (m: DisplayMessage) => DisplayMessage,
): DisplayMessage[] {
  const next = [...messages];
  for (let i = next.length - 1; i >= 0; i--) {
    if (next[i].role === "assistant") {
      next[i] = updater(next[i]);
      break;
    }
  }
  return next;
}
