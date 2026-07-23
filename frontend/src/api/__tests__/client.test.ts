import { describe, expect, it, beforeEach, vi } from "vitest";
import { setTokens, streamSSE } from "../client";

describe("token storage", () => {
  beforeEach(() => localStorage.clear());

  it("stores and clears tokens in localStorage", () => {
    setTokens({ access_token: "a", refresh_token: "b", token_type: "bearer" });
    expect(localStorage.getItem("codesage_tokens")).toContain("access_token");
    setTokens(null);
    expect(localStorage.getItem("codesage_tokens")).toBeNull();
  });
});

describe("streamSSE", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("parses newline-delimited SSE 'data:' frames into events", async () => {
    const encoder = new TextEncoder();
    const frames = [
      'data: {"type":"citations","citations":[]}\n\n',
      'data: {"type":"token","content":"Hello"}\n\n',
      'data: {"type":"token","content":" world"}\n\n',
      'data: {"type":"done"}\n\n',
    ];
    let i = 0;
    const body = {
      getReader() {
        return {
          read: async () => {
            if (i < frames.length) {
              return { value: encoder.encode(frames[i++]), done: false };
            }
            return { value: undefined, done: true };
          },
        };
      },
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      body,
      text: async () => "",
    }) as unknown as typeof fetch;

    const events: unknown[] = [];
    await streamSSE("/chat/sessions/abc/messages", { content: "hi" }, (e) => events.push(e));

    expect(events).toEqual([
      { type: "citations", citations: [] },
      { type: "token", content: "Hello" },
      { type: "token", content: " world" },
      { type: "done" },
    ]);
  });

  it("emits an error event on non-ok response", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      body: null,
      text: async () => "boom",
    }) as unknown as typeof fetch;

    const events: unknown[] = [];
    await streamSSE("/chat/sessions/abc/messages", { content: "hi" }, (e) => events.push(e));

    expect(events).toEqual([{ type: "error", message: "500: boom" }]);
  });
});
