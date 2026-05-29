// Public chat endpoint helper.
//
// Anonymous: no auth cookies required. The shared `api.post` client still
// sends credentials, which is harmless for this endpoint (the backend
// doesn't look at them).

import { api } from "./client";
import type { ChatRequest, ChatResponse } from "./types";

export async function sendChatTurn(
  slug: string,
  body: ChatRequest,
): Promise<ChatResponse> {
  return api.post<ChatResponse>(`/chat/${encodeURIComponent(slug)}`, body);
}
