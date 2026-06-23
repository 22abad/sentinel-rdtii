import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { getStoredToken, isAuthBypassEnabled } from "../hooks/useAuth";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  if (isAuthBypassEnabled()) return <>{children}</>;
  if (!getStoredToken()) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
