const TOKEN_KEY = "support-console-token";
const AGENT_KEY = "support-console-agent";

export type AuthAgent = { id: number; email: string; full_name: string; role: string };

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function getAgent(): AuthAgent | null {
  try {
    const raw = localStorage.getItem(AGENT_KEY);
    return raw ? (JSON.parse(raw) as AuthAgent) : null;
  } catch {
    return null;
  }
}

export function setToken(token: string) {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // localStorage unavailable - session just won't survive a refresh
  }
}

export function setSession(token: string, agent: AuthAgent) {
  setToken(token);
  try {
    localStorage.setItem(AGENT_KEY, JSON.stringify(agent));
  } catch {
    // localStorage unavailable - session just won't survive a refresh
  }
}

export function clearSession() {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(AGENT_KEY);
  } catch {
    // ignore
  }
}

export function isAuthed(): boolean {
  return getToken() !== null;
}
