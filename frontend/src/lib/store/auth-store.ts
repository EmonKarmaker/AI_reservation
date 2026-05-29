"use client";

// Zustand store holding the authenticated user.
//
// Auth tokens live in httpOnly cookies (not readable by JS), so this store
// only holds the user profile returned by /auth/me or /auth/login. On app
// load, call checkAuth() to populate it from the cookie session.

import { create } from "zustand";

import { api } from "@/lib/api/client";
import type { MeResponse, UserOut } from "@/lib/api/types";

interface AuthState {
  user: UserOut | null;
  // null = not yet checked; used to gate the protected layout's first render.
  initialized: boolean;
  loading: boolean;
  setUser: (user: UserOut | null) => void;
  checkAuth: () => Promise<void>;
  logout: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  initialized: false,
  loading: false,

  setUser: (user) => set({ user }),

  checkAuth: async () => {
    set({ loading: true });
    try {
      const data = await api.get<MeResponse>("/auth/me");
      set({ user: data.user, initialized: true, loading: false });
    } catch {
      set({ user: null, initialized: true, loading: false });
    }
  },

  logout: async () => {
    try {
      await api.post("/auth/logout");
    } catch {
      // ignore — clearing local state is what matters
    }
    set({ user: null });
  },
}));
