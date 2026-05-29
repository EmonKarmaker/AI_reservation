"use client";

// Customer-facing chat widget. Talks to POST /chat/{slug}.
//
// Persistence:
// - customer_id is stored per-slug in localStorage as
//   `chat_customer_id_<slug>`. The same browser visiting two demo
//   businesses gets two distinct customer_ids — that's correct: each
//   business owns its own customer rows.
// - We don't persist message history client-side. If the user refreshes,
//   they see an empty chat but the backend conversation continues
//   (customer_id is stable). For a "show me my history" feature, Phase
//   4.8+ will add an endpoint to load past messages.
//
// UX:
// - Optimistic append: user's message renders immediately on send.
// - Loading state shows a "..." placeholder bubble on the AI side.
// - Errors render as a red bubble in-line; user can keep trying.

import { useEffect, useRef, useState, type FormEvent } from "react";

import { sendChatTurn } from "@/lib/api/chat";
import { ApiError, type ChatIntent } from "@/lib/api/types";

interface ChatWidgetProps {
  slug: string;
}

interface Message {
  role: "user" | "assistant" | "error";
  content: string;
  // Set on assistant messages; lets us show intent badge while debugging.
  intent?: ChatIntent;
}

function customerIdKey(slug: string): string {
  return `chat_customer_id_${slug}`;
}

export function ChatWidget({ slug }: ChatWidgetProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [customerId, setCustomerId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const scrollerRef = useRef<HTMLDivElement | null>(null);

  // Load persisted customer_id once on mount. SSR-safe because we only
  // touch window inside useEffect.
  useEffect(() => {
    const stored = window.localStorage.getItem(customerIdKey(slug));
    if (stored) {
      setCustomerId(stored);
    }
  }, [slug]);

  // Auto-scroll to bottom whenever messages or loading state changes.
  useEffect(() => {
    const el = scrollerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages, loading]);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || loading) {
      return;
    }

    // Optimistic append, clear input, mark loading.
    setMessages((m) => [...m, { role: "user", content: trimmed }]);
    setInput("");
    setLoading(true);

    try {
      const response = await sendChatTurn(slug, {
        customer_id: customerId ?? undefined,
        message: trimmed,
      });

      // Persist the returned customer_id so subsequent turns reuse it.
      if (!customerId) {
        window.localStorage.setItem(customerIdKey(slug), response.customer_id);
        setCustomerId(response.customer_id);
      }

      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: response.message,
          intent: response.intent,
        },
      ]);
    } catch (err) {
      const detail =
        err instanceof ApiError
          ? err.detail
          : "Something went wrong. Please try again.";
      setMessages((m) => [...m, { role: "error", content: detail }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex-1 flex flex-col w-full max-w-2xl mx-auto p-4">
      <header className="mb-4 border-b pb-3">
        <h1 className="text-xl font-semibold">AI Receptionist</h1>
        <p className="text-sm text-muted-foreground">/{slug}</p>
      </header>

      <div
        ref={scrollerRef}
        className="flex-1 overflow-y-auto space-y-3 pr-1"
      >
        {messages.length === 0 && !loading && (
          <p className="text-sm text-muted-foreground text-center mt-8">
            Ask anything about services, hours, prices, or booking.
          </p>
        )}

        {messages.map((m, i) => (
          <MessageBubble key={i} message={m} />
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="rounded-2xl bg-gray-100 px-4 py-2 text-gray-500 text-sm">
              ...
            </div>
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="mt-4 flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={loading ? "Waiting..." : "Type your message..."}
          disabled={loading}
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
          autoFocus
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="rounded-lg bg-black text-white px-4 py-2 text-sm font-medium disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}


function MessageBubble({ message }: { message: Message }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="rounded-2xl bg-blue-600 text-white px-4 py-2 max-w-[80%] whitespace-pre-wrap text-sm">
          {message.content}
        </div>
      </div>
    );
  }

  if (message.role === "error") {
    return (
      <div className="flex justify-start">
        <div className="rounded-2xl bg-red-50 border border-red-200 text-red-700 px-4 py-2 max-w-[80%] text-sm">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="rounded-2xl bg-gray-100 px-4 py-2 max-w-[80%] whitespace-pre-wrap text-sm">
        {message.content}
      </div>
    </div>
  );
}
