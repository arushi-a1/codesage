const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface Repository {
  id: string;
  github_url: string;
  full_name: string;
  default_branch: string;
  status: string;
  status_detail: string;
  file_count: number;
  chunk_count: number;
  created_at: string;
}

export interface ChatSession {
  id: string;
  repository_id: string;
  title: string;
  mode: string;
  created_at: string;
}

export interface Citation {
  path: string;
  start_line: number;
  end_line: number;
  symbol: string | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  citations: Citation[];
  created_at: string;
}

function getTokens(): TokenPair | null {
  const raw = localStorage.getItem("codesage_tokens");
  return raw ? JSON.parse(raw) : null;
}

export function setTokens(tokens: TokenPair | null) {
  if (tokens) localStorage.setItem("codesage_tokens", JSON.stringify(tokens));
  else localStorage.removeItem("codesage_tokens");
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const tokens = getTokens();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (tokens) headers["Authorization"] = `Bearer ${tokens.access_token}`;

  const resp = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (resp.status === 401 && tokens) {
    const refreshed = await tryRefresh(tokens.refresh_token);
    if (refreshed) {
      return request<T>(path, options);
    }
    setTokens(null);
    window.location.href = "/login";
    throw new Error("Session expired");
  }
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`${resp.status}: ${body}`);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json();
}

async function tryRefresh(refresh_token: string): Promise<boolean> {
  try {
    const resp = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token }),
    });
    if (!resp.ok) return false;
    const tokens: TokenPair = await resp.json();
    setTokens(tokens);
    return true;
  } catch {
    return false;
  }
}

export const api = {
  register: (email: string, password: string, full_name = "") =>
    request<{ id: string; email: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name }),
    }),

  login: async (email: string, password: string) => {
    const tokens = await request<TokenPair>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setTokens(tokens);
    return tokens;
  },

  logout: () => setTokens(null),

  listRepositories: () => request<Repository[]>("/repositories"),

  importRepository: (github_url: string, branch?: string) =>
    request<Repository>("/repositories", {
      method: "POST",
      body: JSON.stringify({ github_url, branch }),
    }),

  getRepository: (id: string) => request<Repository>(`/repositories/${id}`),

  getRepositoryStatus: (id: string) =>
    request<{ status: string; detail: string }>(`/repositories/${id}/status`),

  reindexRepository: (id: string) =>
    request<Repository>(`/repositories/${id}/reindex`, { method: "POST" }),

  deleteRepository: (id: string) =>
    request<void>(`/repositories/${id}`, { method: "DELETE" }),

  createChatSession: (repository_id: string, mode: string, title?: string) =>
    request<ChatSession>("/chat/sessions", {
      method: "POST",
      body: JSON.stringify({ repository_id, mode, title }),
    }),

  listMessages: (sessionId: string) =>
    request<ChatMessage[]>(`/chat/sessions/${sessionId}/messages`),
};

export interface StreamEvent {
  type: "citations" | "token" | "done" | "error";
  content?: string;
  citations?: Citation[];
  message?: string;
}

/** Streams an SSE response from the chat endpoint, invoking onEvent for
 * each parsed event. Used for both regular chat and PR review. */
export async function streamSSE(
  path: string,
  body: unknown,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const tokens = getTokens();
  const resp = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(tokens ? { Authorization: `Bearer ${tokens.access_token}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });

  if (!resp.ok || !resp.body) {
    const text = await resp.text().catch(() => "");
    onEvent({ type: "error", message: `${resp.status}: ${text}` });
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const line = chunk.trim();
      if (!line.startsWith("data:")) continue;
      const jsonStr = line.slice("data:".length).trim();
      try {
        onEvent(JSON.parse(jsonStr) as StreamEvent);
      } catch {
        // ignore malformed keep-alive lines
      }
    }
  }
}

export function sendChatMessage(
  sessionId: string,
  content: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
) {
  return streamSSE(`/chat/sessions/${sessionId}/messages`, { content }, onEvent, signal);
}

export function reviewPullRequest(
  repoId: string,
  prNumber: number,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
) {
  return streamSSE(
    `/repositories/${repoId}/pull-requests/${prNumber}/review`,
    undefined,
    onEvent,
    signal,
  );
}
