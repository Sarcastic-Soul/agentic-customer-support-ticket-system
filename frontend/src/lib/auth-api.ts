import { request } from "./api";
import type { AuthAgent } from "./auth";

export type LoginResponse = { access_token: string; role: string; full_name: string };

export const authApi = {
  login: (email: string, password: string) =>
    request<LoginResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<AuthAgent>("/api/auth/me"),
};
