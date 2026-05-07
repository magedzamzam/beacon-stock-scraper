"use client";
import { create } from "zustand";
import { api, setToken, type User } from "./api";

interface AuthState {
  user: User | null;
  loading: boolean;
  initialized: boolean;
  init: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, display_name?: string) => Promise<void>;
  logout: () => void;
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  loading: false,
  initialized: false,
  init: async () => {
    if (typeof window === "undefined") { set({ initialized: true }); return; }
    const tok = window.localStorage.getItem("beacon_token");
    if (!tok) { set({ initialized: true }); return; }
    try {
      const user = await api.me();
      set({ user, initialized: true });
    } catch {
      setToken(null);
      set({ user: null, initialized: true });
    }
  },
  login: async (email, password) => {
    set({ loading: true });
    try {
      const res = await api.login(email, password);
      setToken(res.access_token);
      set({ user: res.user });
    } finally {
      set({ loading: false });
    }
  },
  register: async (email, password, display_name) => {
    set({ loading: true });
    try {
      const res = await api.register(email, password, display_name);
      setToken(res.access_token);
      set({ user: res.user });
    } finally {
      set({ loading: false });
    }
  },
  logout: () => {
    setToken(null);
    set({ user: null });
    if (typeof window !== "undefined") window.location.href = "/login";
  },
}));
