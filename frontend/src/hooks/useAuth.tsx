import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, setAuthToken } from "@/lib/api";
import type { UserRole } from "@/types/api";

export type AuthenticatedUser = {
  id: number;
  name: string | null;
  login_id: string;
  role: UserRole;
  partner_id: number | null;
};

type LoginResponse = {
  access_token: string;
  token_type: string;
  user: AuthenticatedUser;
};

type SignupResponse = {
  id: number;
  login_id: string;
  email: string;
  role: UserRole;
};

type AuthContextValue = {
  user: AuthenticatedUser | null;
  login: (loginId: string, password: string) => Promise<void>;
  signup: (params: {
    loginId: string;
    email: string;
    password: string;
    confirmPassword: string;
  }) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

// Holds the logged-in user + JWT for the life of the tab only (see
// lib/api.ts's setAuthToken comment) — reloading the page logs you out.
// That is the deliberate tradeoff for keeping the token out of
// localStorage/sessionStorage, where an XSS payload could read it.
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthenticatedUser | null>(null);

  const login = useCallback(async (loginId: string, password: string) => {
    const response = await api.post<LoginResponse>("/auth/login", {
      login_id: loginId,
      password,
    });
    setAuthToken(response.access_token);
    setUser(response.user);
  }, []);

  const signup = useCallback(
    async ({
      loginId,
      email,
      password,
      confirmPassword,
    }: {
      loginId: string;
      email: string;
      password: string;
      confirmPassword: string;
    }) => {
      // /auth/signup doesn't return a token (SPEC.md §9) — log in right after
      // with the same credentials to actually start the session.
      await api.post<SignupResponse>("/auth/signup", {
        login_id: loginId,
        email,
        password,
        confirm_password: confirmPassword,
      });
      await login(loginId, password);
    },
    [login],
  );

  const logout = useCallback(() => {
    setAuthToken(null);
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, login, signup, logout }), [user, login, signup, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components -- the hook belongs next to its own provider
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside an <AuthProvider>");
  }
  return ctx;
}
