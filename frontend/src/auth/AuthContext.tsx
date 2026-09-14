import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api, clearToken, getToken, setToken } from "../api/client";

interface User {
  username: string;
  role: string;
  /** Whether this person may see organisation-wide reporting. Decided by the
   *  server on every request — never trust this for authorisation, it only
   *  drives what the UI offers. */
  can_view_org: boolean;
  /** Whether there is a directory identity behind this session, and therefore
   *  a personal view of "agents you created". */
  has_personal_view: boolean;
}
interface AuthState {
  user: User | null;
  loading: boolean;
  ssoError: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState>(null!);
export const useAuth = () => useContext(AuthContext);

interface TokenResp {
  access_token: string;
  username: string;
  role: string;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [ssoError, setSsoError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      // A completed Entra sign-in hands the token back in the URL fragment.
      // Fragments never reach the server, so the token cannot appear in access
      // logs or a Referer header. Consume it and strip it from the address bar.
      const hash = window.location.hash;
      if (hash.startsWith("#sso=")) {
        setToken(decodeURIComponent(hash.slice("#sso=".length)));
        window.history.replaceState(null, "", window.location.pathname);
      } else if (hash.startsWith("#sso_error=")) {
        setSsoError(decodeURIComponent(hash.slice("#sso_error=".length)));
        window.history.replaceState(null, "", window.location.pathname);
      }

      if (getToken()) {
        try {
          const me = await api.get<User>("/auth/me");
          setUser(me);
        } catch {
          clearToken();
        }
      }
      setLoading(false);
    })();
  }, []);

  const login = async (username: string, password: string) => {
    const r = await api.post<TokenResp>("/auth/login", { username, password });
    setToken(r.access_token);
    // The login response predates the capability flags, so ask /auth/me rather
    // than guessing them — the org gate is evaluated server-side per request.
    try {
      setUser(await api.get<User>("/auth/me"));
    } catch {
      setUser({
        username: r.username,
        role: r.role,
        can_view_org: r.role === "admin",
        has_personal_view: false,
      });
    }
  };

  const logout = () => {
    clearToken();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, ssoError, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
