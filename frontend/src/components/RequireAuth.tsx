import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";

// Route guard: redirects to /login if no user is logged in, remembering
// where they were headed so Login can send them back after a successful
// login. Since the token lives in memory only (see useAuth.tsx), this also
// means a page reload always bounces back to /login — expected, not a bug.
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const location = useLocation();

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}
