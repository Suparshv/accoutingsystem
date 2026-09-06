import { LogOut, Menu } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";
import type { UserRole } from "@/types/api";

type TopbarProps = {
  onMenuClick: () => void;
};

const ROLE_LABELS: Record<UserRole, string> = {
  admin: "Administrator",
  accountant: "Accountant",
  contact: "Portal user",
};

export function Topbar({ onMenuClick }: TopbarProps) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  // Navigate explicitly rather than leaving RequireAuth to bounce the now
  // user-less app to /login. RequireAuth's redirect carries a `from` location
  // so it can return you there after signing in — correct when a session
  // expired mid-task, wrong after a deliberate log out: the next person to
  // sign in would land on the previous user's last page, which for a contact
  // could be a route their role cannot even load. Logging out starts clean.
  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-background px-4">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="md:hidden"
        onClick={onMenuClick}
        aria-label="Open menu"
      >
        <Menu className="h-5 w-5" />
      </Button>

      <span className="text-sm font-medium text-text_secondary">
        Urban Furniture Accounting
      </span>

      {user && (
        <div className="ml-auto flex items-center gap-3">
          {/* Hidden on the narrowest screens so the log out control itself
              always has room — who you are is recoverable, being unable to
              leave is not. */}
          <span className="hidden text-right leading-tight sm:block">
            <span className="block text-sm font-medium text-text_primary">
              {user.name || user.login_id}
            </span>
            <span className="block text-xs text-text_secondary">
              {ROLE_LABELS[user.role]}
            </span>
          </span>

          <Button type="button" variant="outline" size="sm" onClick={handleLogout}>
            <LogOut className="h-4 w-4 sm:mr-2" />
            <span className="hidden sm:inline">Log out</span>
          </Button>
        </div>
      )}
    </header>
  );
}
