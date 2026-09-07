import { clearSession, getToken } from "./auth";

/** Shared fetch wrapper: attaches the JWT (when present) and redirects to
 * /login on a 401 - every console/admin route requires auth (Stage 9). */
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });

  if (res.status === 401) {
    clearSession();
    if (location.pathname !== "/login") {
      location.href = `/login?next=${encodeURIComponent(location.pathname + location.search)}`;
    }
    throw new Error("401 unauthorized");
  }

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}
