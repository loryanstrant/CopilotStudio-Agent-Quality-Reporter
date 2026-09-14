import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api, clearToken, getToken, setToken } from "../api/client";

interface User {
  username: string;
  role: string;
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
    setUser({ username: r.username, role: r.role });
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
