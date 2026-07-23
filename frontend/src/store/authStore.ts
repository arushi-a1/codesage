import { create } from "zustand";
import { api, setTokens } from "../api/client";

interface AuthState {
  isAuthenticated: boolean;
  email: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  isAuthenticated: !!localStorage.getItem("codesage_tokens"),
  email: localStorage.getItem("codesage_email"),

  login: async (email, password) => {
    await api.login(email, password);
    localStorage.setItem("codesage_email", email);
    set({ isAuthenticated: true, email });
  },

  register: async (email, password, fullName) => {
    await api.register(email, password, fullName);
  },

  logout: () => {
    setTokens(null);
    localStorage.removeItem("codesage_email");
    set({ isAuthenticated: false, email: null });
  },
}));
